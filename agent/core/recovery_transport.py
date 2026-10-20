"""Protocol-2 adapter for the existing workbench authority; no controller creation.

Caller injects a reviewed RecoveryControl instance. This module does not locate
or import workbench code, read credentials, run a service, or enable a worker.
"""
from fastapi import HTTPException


def require_protocol(controller):
    capability=getattr(controller,'request_capabilities',lambda:{})()
    if (not isinstance(capability,dict) or capability.get('protocol')!=2
            or capability.get('expiryChecked') is not True or capability.get('cancelUnderAuthorityLock') is not True):
        raise HTTPException(503,'恢复控制器缺少过期/撤回协议，安全继续已禁用')


class RecoveryTransport:
    def __init__(self,controller,namespace):
        require_protocol(controller)
        self.controller=controller
        self.namespace=namespace

    def submit(self,target):
        n=self.namespace
        command_id=str(target.get('commandId') or '')
        command=n['read_control_command'](command_id)
        if not command or not command.get('expiresAt'):
            raise HTTPException(409,'缺少原命令有效期，须按原命令编号对账')
        if n['_continue_target_signature'](command)!=n['_continue_target_signature'](target):
            raise HTTPException(409,'恢复请求与原命令目标不一致')
        # Preserve original deadline and creation time. A retry must never
        # create a new 300-second window or change the authoritative identity.
        request={**target,'commandId':command_id,'command':'continue_current_project',
                 'requestedAt':command['requestedAt'],'expiresAt':command['expiresAt'],
                 'requestedBy':'cloud_agent'}
        try:
            require_protocol(self.controller)
            queued=self.controller.enqueue_request(request)
        except HTTPException:raise
        except (OSError,ValueError,RuntimeError) as error:
            raise HTTPException(503,'恢复请求未获权威确认，请按原编号查询') from error
        if queued.get('commandId')!=command_id or queued.get('state') not in {'requested','delivered'}:
            raise HTTPException(409,'恢复请求已过期、撤回或待人工对账')
        return {'accepted':True,'commandId':command_id,'state':queued['state'],
                **n['_ensure_workbench_for_continue']()}

    def cancel(self,command_id,request):
        n=self.namespace
        n['require_control_permission'](request)
        with n['CONTROL_COMMAND_LOCK']:
            command=n['read_control_command'](command_id)
            if not command:raise HTTPException(404,'未找到该安全继续命令')
            if command.get('state') in {'completed','blocked','expired','cancelled'}:
                return n['sanitize_public_value'](command)
            if command.get('state') in {'executing','unknown'}:
                raise HTTPException(409,'执行中或结果不明，只能按原编号对账')
            try:
                require_protocol(self.controller)
                cancelled=self.controller.cancel_request(command_id,expected_target={
                    key:command.get(key) for key in ('taskId','batchId','runGroupId','productionDate',
                         'manifestId','attemptId','batchKind','selectedProjects','step','stableRecoveryKey')})
            except HTTPException:raise
            except (OSError,ValueError,RuntimeError) as error:
                raise HTTPException(409,'权威控制器未确认撤回，只能按原编号查询与对账') from error
            if cancelled.get('state')!='cancelled' or cancelled.get('commandId')!=command_id:
                raise HTTPException(409,'未获得原命令撤回确认')
            # Never claim cancellation before the independent request source
            # and its matching unstarted mailbox are durably retired by RC.
            command.update(state='cancelled',finishedAt=n['now_iso'](),message='权威控制器已确认撤回，不会延迟执行')
            n['write_control_command'](command)
            return n['sanitize_public_value'](command)
