using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

// The only process initially assigned is created suspended. Descendants inherit
// this non-breakaway job. Closing the wrapper's last job handle kills the tree.
public static class OpsAgentJob {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime,JobTime; public uint Flags;
        public UIntPtr MinWorkingSet,MaxWorkingSet; public uint ActiveLimit;
        public UIntPtr Affinity; public uint Priority,Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOperations,WriteOperations,OtherOperations,ReadBytes,WriteBytes,OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory,JobMemory,PeakProcessMemory,PeakJobMemory;
    }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct StartupInfo {
        public int Size; public string Reserved,Desktop,Title;
        public uint X,Y,XSize,YSize,XChars,YChars,Fill,Flags;
        public short ShowWindow,ReservedSize; public IntPtr ReservedBytes,Input,Output,Error;
    }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
        public IntPtr Process,Thread; public uint ProcessId,ThreadId;
    }
    [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes {
        public int Size; public IntPtr Descriptor; public int Inherit;
    }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref ExtendedLimits info,uint length);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string executable,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string directory,ref StartupInfo startup,out ProcessInfo process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(string name,uint access,uint share,ref SecurityAttributes attributes,uint disposition,uint flags,IntPtr template);

    static void Require(bool result) { if (!result) throw new Win32Exception(Marshal.GetLastWin32Error()); }
    static void Status(string directory,uint child,string phase,uint code,int retrySeconds=0) {
        string target=Path.Combine(directory,"task-job.json");
        string temporary=target+"."+Guid.NewGuid().ToString("N")+".tmp";
        string json="{\"schema\":2,\"wrapperPid\":"+System.Diagnostics.Process.GetCurrentProcess().Id+
            ",\"wrapperCreationFileTime\":"+System.Diagnostics.Process.GetCurrentProcess().StartTime.ToUniversalTime().ToFileTimeUtc()+
            ",\"launcherPid\":"+child+",\"phase\":\""+phase+"\",\"exitCode\":"+code+
            ",\"retryAfterSeconds\":"+retrySeconds+",\"retryAt\":\""+(retrySeconds>0?DateTime.UtcNow.AddSeconds(retrySeconds).ToString("o"):"")+"\""+
            ",\"observedAt\":\""+DateTime.UtcNow.ToString("o")+"\"}";
        File.WriteAllText(temporary,json,new UTF8Encoding(false));
        if (File.Exists(target)) File.Replace(temporary,target,null); else File.Move(temporary,target);
    }
    static bool StopRequested(string state) {
        return File.Exists(Path.Combine(state,"maintenance.json")) || File.Exists(Path.Combine(state,"stop-request.json"));
    }
    public static int Supervise(string python,string root,string state,int retryMilliseconds) {
        if (retryMilliseconds<1) throw new ArgumentOutOfRangeException("retryMilliseconds");
        Directory.CreateDirectory(state);
        // The mutex prevents direct invocations from creating competing supervisors.
        byte[] hash;
        using (var sha=System.Security.Cryptography.SHA256.Create()) {
            hash=sha.ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(state).ToLowerInvariant()));
        }
        string name="Local\\OpsAgentSupervisor-"+BitConverter.ToString(hash).Replace("-","");
        using (var mutex=new System.Threading.Mutex(false,name)) {
            bool owned=false;
            try {
                try { owned=mutex.WaitOne(0); } catch (System.Threading.AbandonedMutexException) { owned=true; }
                if (!owned) return 0; // Never overwrite the live supervisor's status.
                while (true) {
                    if (StopRequested(state)) { Status(state,0,"maintenance-blocked",0);return 0; }
                    int code;
                    try { code=Run(python,root,state); }
                    catch { code=1;Status(state,0,"launch-failed",1); }
                    if (StopRequested(state) || code==0) { Status(state,0,"stopped",(uint)code);return 0; }
                    // Run has closed its Job, so no descendant survives into backoff.
                    Status(state,0,"restart-wait",unchecked((uint)code),(retryMilliseconds+999)/1000);
                    var delay=System.Diagnostics.Stopwatch.StartNew();
                    while (delay.ElapsedMilliseconds<retryMilliseconds) {
                        if (StopRequested(state)) { Status(state,0,"stopped",unchecked((uint)code));return 0; }
                        long remaining=retryMilliseconds-delay.ElapsedMilliseconds;
                        if (remaining<=0) break;
                        System.Threading.Thread.Sleep((int)Math.Min(250,remaining));
                    }
                }
            } finally { if (owned) mutex.ReleaseMutex(); }
        }
    }
    public static int Run(string python,string root,string state) {
        if (python.Contains("\"") || root.Contains("\"")) throw new ArgumentException("Invalid path");
        Directory.CreateDirectory(state);
        IntPtr job=IntPtr.Zero,input=IntPtr.Zero; ProcessInfo child=new ProcessInfo();
        try {
            job=CreateJobObject(IntPtr.Zero,null);
            Require(job!=IntPtr.Zero);
            ExtendedLimits limits=new ExtendedLimits(); limits.Basic.Flags=0x2000; // KILL_ON_JOB_CLOSE; no breakaway flags
            Require(SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(ExtendedLimits))));
            SecurityAttributes security=new SecurityAttributes();security.Size=Marshal.SizeOf(typeof(SecurityAttributes));security.Inherit=1;
            input=CreateFile("NUL",0x80000000,3,ref security,3,0,IntPtr.Zero);
            Require(input!=new IntPtr(-1));
            using (FileStream output=new FileStream(Path.Combine(state,"task.stdout.log"),FileMode.Create,FileAccess.Write,FileShare.ReadWrite))
            using (FileStream error=new FileStream(Path.Combine(state,"task.stderr.log"),FileMode.Create,FileAccess.Write,FileShare.ReadWrite)) {
                Require(SetHandleInformation(output.SafeFileHandle.DangerousGetHandle(),1,1));
                Require(SetHandleInformation(error.SafeFileHandle.DangerousGetHandle(),1,1));
                StartupInfo startup=new StartupInfo(); startup.Size=Marshal.SizeOf(typeof(StartupInfo));startup.Flags=0x100;
                startup.Input=input;startup.Output=output.SafeFileHandle.DangerousGetHandle();startup.Error=error.SafeFileHandle.DangerousGetHandle();
                StringBuilder command=new StringBuilder("\""+python+"\" -B -m agent.launcher");
                Require(CreateProcess(python,command,IntPtr.Zero,IntPtr.Zero,true,0x08000004,IntPtr.Zero,root,ref startup,out child));
                if (!AssignProcessToJobObject(job,child.Process)) {
                    int failure=Marshal.GetLastWin32Error();TerminateProcess(child.Process,1);throw new Win32Exception(failure);
                }
                Status(state,child.ProcessId,"starting",0);
                Require(ResumeThread(child.Thread)!=UInt32.MaxValue);
                Status(state,child.ProcessId,"running",0);
                Require(WaitForSingleObject(child.Process,UInt32.MaxValue)==0);
                uint code;Require(GetExitCodeProcess(child.Process,out code));
                Status(state,child.ProcessId,"exited",code);
                return unchecked((int)code);
            }
        } finally {
            // Kill any remaining descendants before losing the last parent handle.
            if (job!=IntPtr.Zero) CloseHandle(job);
            if (child.Thread!=IntPtr.Zero) CloseHandle(child.Thread);
            if (child.Process!=IntPtr.Zero) CloseHandle(child.Process);
            if (input!=IntPtr.Zero && input!=new IntPtr(-1)) CloseHandle(input);
        }
    }
}
