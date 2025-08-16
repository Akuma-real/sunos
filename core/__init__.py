"""核心模块包 - 统一导出所有核心功能

提供便捷的导入接口，简化模块使用
"""

# 数据库层
from .database import SunosDatabase

# 权限管理
from .permissions import (
    PermissionLevel,
    PermissionManager,
    admin_required,
    group_only,
    super_admin_required,
    get_user_permission_level,
    check_permission,
    check_admin_permission,
    check_group_chat,
    check_real_group_admin_permission,
    check_admin_permission_async
)

# 平台适配
from .platform import PlatformAdapter

# 业务服务层
from .services import (
    KeywordService,
    WelcomeService,
    BlacklistService,
    GroupService
)

# 事件处理器
from .handlers import (
    GroupEventHandler,
    AutoReplyHandler
)

# 工具类
from .utils import (
    ValidationUtils,
    MessageBuilder,
    NotificationManager,
    SystemUtils,
    HelpTextBuilder
)

# 导出列表
__all__ = [
    # 数据库
    'SunosDatabase',
    
    # 权限管理
    'PermissionLevel',
    'PermissionManager',
    'admin_required',
    'group_only', 
    'super_admin_required',
    'get_user_permission_level',
    'check_permission',
    'check_admin_permission',
    'check_group_chat',
    'check_real_group_admin_permission',
    'check_admin_permission_async',
    
    # 平台适配
    'PlatformAdapter',
    
    # 业务服务
    'KeywordService',
    'WelcomeService',
    'BlacklistService',
    'GroupService',
    
    # 事件处理
    'GroupEventHandler',
    'AutoReplyHandler',
    
    # 工具类
    'ValidationUtils',
    'MessageBuilder',
    'NotificationManager',
    'SystemUtils',
    'HelpTextBuilder'
]