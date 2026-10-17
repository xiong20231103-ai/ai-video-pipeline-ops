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
    static void Status(string directory,uint child,string phase,uint code) {
        string target=Path.Combine(directory,"task-job.json");
        string temporary=target+"."+Guid.NewGuid().ToString("N")+".tmp";
        string json="{\"schema\":1,\"wrapperPid\":"+System.Diagnostics.Process.GetCurrentProcess().Id+
            ",\"launcherPid\":"+child+",\"phase\":\""+phase+"\",\"exitCode\":"+code+
            ",\"observedAt\":\""+DateTime.UtcNow.ToString("o")+"\"}";
        File.WriteAllText(temporary,json,new UTF8Encoding(false));
        if (File.Exists(target)) File.Replace(temporary,target,null); else File.Move(temporary,target);
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
