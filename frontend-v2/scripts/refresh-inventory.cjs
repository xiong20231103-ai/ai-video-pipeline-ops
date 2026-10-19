// Refresh only excerpts/coordinates. Preserve IDs, coverage, PRs and evidence.
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const root=path.resolve(__dirname,'../..'),file=path.join(root,'docs/v2/inventory.json'),md=path.join(root,'docs/v2/FUNCTIONAL_INVENTORY.md');
const before=fs.readFileSync(file,'utf8'),data=JSON.parse(before),old=fs.readFileSync(md,'utf8'),lines=old.split('\n');
const files=[...new Set(data.groups.functions.map(row=>row.source))];let refreshed=0;
for(const sourcePath of files){
 const text=fs.readFileSync(path.join(root,sourcePath),'utf8'),source=ts.createSourceFile(sourcePath,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS),nodes=[];
 const visit=node=>{if(ts.isFunctionLike(node)&&node.body)nodes.push(node);ts.forEachChild(node,visit)};visit(source);
 const entries=data.groups.functions.filter(row=>row.source===sourcePath);
 if(nodes.length!==entries.length)throw Error('Function count changed; regenerate inventory deliberately: '+sourcePath);
 entries.forEach((entry,index)=>{
  const node=nodes[index],start=source.getLineAndCharacterOfPosition(node.getStart(source)),end=source.getLineAndCharacterOfPosition(node.getEnd());
  const parent=node.parent,name=node.name?.getText(source)||(ts.isVariableDeclaration(parent)?parent.name.getText(source):ts.isPropertyAssignment(parent)?parent.name.getText(source):'匿名回调@'+(start.line+1));
  if(entry.line!==start.line+1||entry.name!==name)throw Error('Inventory identity moved: '+entry.id);
  // The previous generator climbed up to three ancestors and often reached
  // the outer IIFE/file preamble. Use the actual function node exclusively.
  entry.detail=node.getText(source).replace(/\s+/g,' ').slice(0,430);
  entry.excerptStartLine=start.line+1;entry.excerptStartColumn=start.character+1;entry.excerptEndLine=end.line+1;
  const i=lines.findIndex(line=>new RegExp('^- \\[[ x]\\] \\*\\*'+entry.id+'\\*\\*').test(line));
  if(i<0)throw Error('Missing Markdown row: '+entry.id);
  const marker='原实现：`',a=lines[i+1].indexOf(marker)+marker.length,b=lines[i+1].indexOf('`',a);
  if(a<marker.length||b<a)throw Error('Invalid excerpt row: '+entry.id);
  lines[i+1]=lines[i+1].slice(0,a)+entry.detail.replaceAll('`','ˋ').replaceAll('|','¦')+lines[i+1].slice(b);
  refreshed++;
 });
}
const next=JSON.stringify(data,null,2)+'\n',markdown=lines.join('\n');
if(process.argv.includes('--check')){
 if(JSON.stringify(data)!==JSON.stringify(JSON.parse(before))||markdown.replace(/\r\n/g,'\n')!==old.replace(/\r\n/g,'\n'))throw Error('Inventory excerpts stale; run npm run inventory:refresh');
}else{fs.writeFileSync(file,next);fs.writeFileSync(md,markdown);}
console.log(JSON.stringify({functionExcerpts:refreshed,coveragePreserved:true,checkOnly:process.argv.includes('--check')}));
