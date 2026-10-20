"""Single-threaded replay I/O guard for pinned, trusted legacy code.

Explicit aliases redirect captured production path *strings* into scratch;
they never authorize I/O to a live root. This is not a sandbox for arbitrary
Python/native code. Run only the source hash pinned by the reviewed oracle.
"""
import builtins,io,os,sqlite3,sys,stat,types,ntpath
from pathlib import Path
from urllib.parse import urlsplit,unquote
from unittest.mock import patch

class SandboxIO:
    def __init__(self,root,stack,filesystem=None,content_files=(),aliases=None):
        self.root=Path(root).resolve();self.lexical_root=Path(os.path.abspath(root));self.stack=stack;self.denied=[]
        self.filesystem=filesystem or {};self.content_files=set(content_files)
        self.aliases=sorted((aliases or {}).items(),key=lambda item:len(item[0]),reverse=True)
        self.read_roots=[self.root,Path(__file__).resolve().parents[2],Path(sys.base_prefix).resolve()]
        self.read_roots.extend(Path(p).resolve() for p in sys.path if p and ('site-packages' in p or '.test-deps' in p))
    def translate(self,path):
        if isinstance(path,int):return path
        raw=os.fsdecode(path)
        if raw.startswith('file:'):
            raw=unquote(urlsplit(raw).path)
            if os.name=='nt' and len(raw)>3 and raw[0]=='/' and raw[2]==':':raw=raw[1:]
        normalized=ntpath.normpath(raw).replace(chr(92),'/')
        for old,new in self.aliases:
            prefix=ntpath.normpath(old).replace(chr(92),'/').rstrip('/')
            if normalized.casefold()==prefix.casefold():return self.root/new
            if normalized.casefold().startswith(prefix.casefold()+'/'):
                return self.root/new/normalized[len(prefix)+1:]
        return Path(raw)
    def deny(self,operation):
        self.denied.append({'operation':operation,'outsideScratch':True})
        raise PermissionError('replay_io_outside_snapshot')
    def check(self,path,write=False,content=False):
        if isinstance(path,int):return path
        if os.fsdecode(path) in {':memory:',os.devnull}:return path
        translated=self.translate(path)
        candidate=Path(os.path.abspath(translated))
        roots=[self.root] if write else self.read_roots
        if not any(candidate==base or candidate.is_relative_to(base) for base in [*roots,self.lexical_root]):self.deny('write' if write else 'read')
        candidate=Path(os.path.realpath(candidate))
        if not any(candidate==base or candidate.is_relative_to(base) for base in roots):self.deny('link-escape')
        if candidate.is_relative_to(self.root):
            name=candidate.relative_to(self.root).as_posix()
            if name in self.filesystem and name not in self.content_files and self.filesystem[name]['kind']=='file' and (content or write):
                self.denied.append({'operation':'metadata-only-content','outsideScratch':False})
                raise PermissionError('metadata_only_content_unavailable')
        return translated
    def install(self):
        original_open=builtins.open;original_io=io.open;original_os_open=os.open;original_connect=sqlite3.connect
        def file_open(path,mode='r',*args,**kwargs):return original_open(self.check(path,any(c in mode for c in 'wax+'),True),mode,*args,**kwargs)
        def io_open(path,mode='r',*args,**kwargs):return original_io(self.check(path,any(c in mode for c in 'wax+'),True),mode,*args,**kwargs)
        def os_open(path,flags,*args,**kwargs):
            if kwargs.get('dir_fd') is not None:self.deny('directory-descriptor')
            return original_os_open(self.check(path,bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)),True),flags,*args,**kwargs)
        def connect(path,*args,**kwargs):
            readonly=str(path).startswith('file:') and 'mode=ro' in str(path)
            mapped=self.check(path,not readonly,True)
            if str(path).startswith('file:'):
                parsed=urlsplit(path);mapped=Path(mapped).absolute().as_uri()+('?' + parsed.query if parsed.query else '')
            return original_connect(mapped,*args,**kwargs)
        for owner,name,fn in [(builtins,'open',file_open),(io,'open',io_open),(os,'open',os_open),(sqlite3,'connect',connect)]:self.stack.enter_context(patch.object(owner,name,fn))
        for name in ('resolve','stat','iterdir','glob','rglob'):
            original=getattr(Path,name)
            def wrapped(path,*args,_original=original,_name=name,**kwargs):
                mapped=self.check(path)
                if _name=='stat':
                    candidate=Path(os.path.realpath(os.path.abspath(mapped)))
                    if candidate.is_relative_to(self.root):
                        node=self.filesystem.get(candidate.relative_to(self.root).as_posix())
                        if node:
                            ns=node.get('mtimeNs',0);seconds=ns/10**9
                            return types.SimpleNamespace(st_mode=stat.S_IFDIR if node['kind']=='directory' else stat.S_IFREG,st_size=node.get('size',0),st_mtime=seconds,st_mtime_ns=ns,st_ctime=seconds,st_ctime_ns=ns,st_atime=seconds,st_atime_ns=ns)
                return _original(Path(mapped),*args,**kwargs)
            self.stack.enter_context(patch.object(Path,name,wrapped))
        for name in ('mkdir','unlink','rmdir','rename','replace','remove'):
            original=getattr(os,name)
            def mutation(path,*args,_original=original,_name=name,**kwargs):
                if any(kwargs.get(key) is not None for key in ('dir_fd','src_dir_fd','dst_dir_fd')):self.deny('directory-descriptor')
                mapped=self.check(path,True)
                if _name in {'rename','replace'}:args=(self.check(args[0],True),*args[1:])
                return _original(mapped,*args,**kwargs)
            self.stack.enter_context(patch.object(os,name,mutation))
        for name in ('symlink','link'):
            self.stack.enter_context(patch.object(os,name,side_effect=lambda *args,**kwargs:self.deny('create-link')))
        return self
