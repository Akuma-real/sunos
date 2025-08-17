"""业务服务层 - 实现核心业务逻辑

每个服务类专注单一职责，提供清晰的业务接口
"""
from typing import List, Optional, Tuple
from .database import SunosDatabase
from .utils import ValidationUtils
from astrbot.api import logger


class KeywordService:
    """词库服务 - 处理关键词相关业务逻辑"""
    
    def __init__(self, database: SunosDatabase):
        self.db = database

    def add_keyword(self, keyword: str, reply: str) -> Tuple[bool, str]:
        """添加关键词
        
        Args:
            keyword: 关键词
            reply: 回复内容
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        # 输入验证
        keyword_valid, keyword_error = ValidationUtils.validate_input_length(
            keyword, 100, "关键词"
        )
        if not keyword_valid:
            return False, keyword_error

        reply_valid, reply_error = ValidationUtils.validate_input_length(
            reply, 1000, "回复内容"
        )
        if not reply_valid:
            return False, reply_error

        # 处理换行符
        reply = reply.replace("\\n", "\n")

        try:
            if self.db.add_keyword(keyword, reply):
                return True, f"成功添加词库:\n关键词: {keyword}\n回复: {reply}"
            else:
                return False, f"关键词 '{keyword}' 已存在！"
        except Exception as e:
            logger.error(f"添加关键词失败: {e}")
            return False, "添加词库失败，请稍后重试"

    def delete_keyword(self, index: int) -> Tuple[bool, str]:
        """删除关键词
        
        Args:
            index: 词库序号（1开始）
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        keywords = self.db.get_all_keywords()
        if not keywords:
            return False, "当前没有词库条目"

        if index < 1 or index > len(keywords):
            return False, f"序号错误，请输入 1-{len(keywords)} 之间的数字"

        keyword_data = keywords[index - 1]
        if self.db.delete_keyword(keyword_data[0]):
            return True, f"成功删除词库: {keyword_data[1]}"
        else:
            return False, "删除失败"

    def get_keyword_list(self) -> Tuple[bool, str]:
        """获取词库列表
        
        Returns:
            tuple: (是否成功, 结果消息)
        """
        keywords = self.db.get_all_keywords()
        if not keywords:
            return False, "当前没有词库条目"

        result = f"📚 词库列表 (共 {len(keywords)} 条):\n\n"
        for i, (_, keyword, reply) in enumerate(keywords, 1):
            display_reply = reply[:50] + "..." if len(reply) > 50 else reply
            display_reply = display_reply.replace("\n", "\\n")
            result += f"{i}. {keyword} → {display_reply}\n"

        result += "\n使用 /sunos ck del <序号> 删除词库"
        return True, result

    def find_keyword_reply(self, message: str) -> Optional[str]:
        """查找关键词回复
        
        Args:
            message: 用户消息
            
        Returns:
            str: 回复内容，如果没有匹配则返回None
        """
        return self.db.find_keyword_reply(message.strip())


class WelcomeService:
    """欢迎语服务 - 处理欢迎语相关业务逻辑"""
    
    def __init__(self, database: SunosDatabase):
        self.db = database

    def set_welcome_message(self, group_id: str, message: str) -> Tuple[bool, str]:
        """设置欢迎语
        
        Args:
            group_id: 群组ID
            message: 欢迎语内容
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        # 输入验证
        msg_valid, msg_error = ValidationUtils.validate_input_length(
            message, 500, "欢迎语"
        )
        if not msg_valid:
            return False, msg_error

        # 处理换行符
        message = message.replace("\\n", "\n")

        try:
            if self.db.set_welcome_message(group_id, message):
                return True, f"成功设置欢迎语:\n{message}"
            else:
                return False, "设置欢迎语失败"
        except Exception as e:
            logger.error(f"设置欢迎语失败: {e}")
            return False, "设置欢迎语失败，请稍后重试"

    def delete_welcome_message(self, group_id: str) -> Tuple[bool, str]:
        """删除欢迎语
        
        Args:
            group_id: 群组ID
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        if self.db.delete_welcome_message(group_id):
            return True, "成功删除当前群的欢迎语设置"
        else:
            return False, "删除失败或当前群未设置欢迎语"

    def get_welcome_message(self, group_id: str) -> Tuple[bool, str]:
        """获取欢迎语
        
        Args:
            group_id: 群组ID
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        welcome_msg = self.db.get_welcome_message(group_id)
        if welcome_msg:
            return True, f"当前群欢迎语:\n{welcome_msg}"
        else:
            return False, "当前群未设置欢迎语"

    def get_welcome_message_raw(self, group_id: str) -> Optional[str]:
        """获取原始欢迎语内容
        
        Args:
            group_id: 群组ID
            
        Returns:
            str: 欢迎语内容，如果没有则返回None
        """
        return self.db.get_welcome_message(group_id)


class BlacklistService:
    """黑名单服务 - 处理黑名单相关业务逻辑"""
    
    def __init__(self, database: SunosDatabase):
        self.db = database

    def add_user_to_blacklist(
        self, user_id: str, added_by: str, group_id: str = None, reason: str = ""
    ) -> Tuple[bool, str]:
        """添加用户到黑名单
        
        Args:
            user_id: 要添加的用户ID
            added_by: 添加者的用户ID
            group_id: 群组ID，None表示全局黑名单
            reason: 添加原因
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        # 输入验证
        if not ValidationUtils.validate_user_id(user_id):
            return False, "用户ID必须是数字"

        reason_valid, reason_error = ValidationUtils.validate_input_length(
            reason, 200, "原因"
        )
        if not reason_valid:
            return False, reason_error

        try:
            # 检查用户是否已在黑名单中
            if self.db.is_in_blacklist(user_id, group_id):
                scope_text = (
                    "全局黑名单" if group_id is None else f"群组 {group_id} 黑名单"
                )
                return False, f"用户 {user_id} 已在{scope_text}中"

            # 添加到黑名单
            if self.db.add_to_blacklist(user_id, added_by, group_id, reason):
                scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                reason_text = f"，原因：{reason}" if reason else ""
                return True, f"成功添加用户 {user_id} 到{scope_text}{reason_text}"
            else:
                return False, "添加黑名单失败，请稍后重试"

        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False, "添加黑名单失败，请稍后重试"

    def remove_user_from_blacklist(
        self, user_id: str, group_id: str = None
    ) -> Tuple[bool, str]:
        """从黑名单移除用户
        
        Args:
            user_id: 要移除的用户ID
            group_id: 群组ID，None表示全局黑名单
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        if not ValidationUtils.validate_user_id(user_id):
            return False, "用户ID必须是数字"

        try:
            # 检查用户是否在黑名单中
            if not self.db.is_in_blacklist(user_id, group_id):
                scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                return False, f"用户 {user_id} 不在{scope_text}中"

            # 从黑名单移除
            if self.db.remove_from_blacklist(user_id, group_id):
                scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                return True, f"成功从{scope_text}移除用户 {user_id}"
            else:
                return False, "移除黑名单失败，请稍后重试"

        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False, "移除黑名单失败，请稍后重试"

    def check_user_blacklist_status(
        self, user_id: str, group_id: str = None
    ) -> Tuple[bool, str]:
        """检查用户黑名单状态
        
        Args:
            user_id: 用户ID
            group_id: 群组ID
            
        Returns:
            tuple: (是否在黑名单, 状态消息)
        """
        if not ValidationUtils.validate_user_id(user_id):
            return False, "用户ID必须是数字"

        try:
            blacklist_info = self.db.get_user_blacklist_info(user_id, group_id)

            if blacklist_info:
                _, _, bl_group_id, reason, added_by, created_at = blacklist_info
                scope_text = (
                    "全局黑名单"
                    if bl_group_id is None
                    else f"群组 {bl_group_id} 黑名单"
                )
                reason_text = f"，原因：{reason}" if reason else ""
                return (
                    True,
                    f"用户 {user_id} 在{scope_text}中{reason_text}\n添加者：{added_by}\n添加时间：{created_at}",
                )
            else:
                return False, f"用户 {user_id} 不在黑名单中"

        except Exception as e:
            logger.error(f"检查黑名单状态失败: {e}")
            return False, "检查黑名单状态失败，请稍后重试"

    def get_blacklist(self, group_id: str = None) -> Tuple[bool, str]:
        """获取黑名单列表
        
        Args:
            group_id: 群组ID
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            blacklist = self.db.get_blacklist(group_id, limit=20)  # 限制显示20条

            if not blacklist:
                return self._handle_empty_blacklist(group_id)

            return self._format_blacklist_result(blacklist, group_id)

        except Exception as e:
            logger.error(f"获取黑名单列表失败: {e}")
            return False, "获取黑名单列表失败，请稍后重试"

    def _handle_empty_blacklist(self, group_id: str = None) -> Tuple[bool, str]:
        """处理空黑名单情况
        
        Args:
            group_id: 群组ID
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
        return False, f"{scope_text}为空"

    def _format_blacklist_result(self, blacklist: List, group_id: str = None) -> Tuple[bool, str]:
        """格式化黑名单结果
        
        Args:
            blacklist: 黑名单数据列表
            group_id: 群组ID
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        scope_text = "全局黑名单" if group_id is None else f"群组 {group_id} 黑名单"
        result = f"🚫 {scope_text} (显示前20条):\n\n"

        # 格式化每个黑名单条目
        result += self._format_blacklist_entries(blacklist)

        # 添加统计信息和使用说明
        result += f"\n总计：{len(blacklist)} 条记录"
        result += "\n使用 /sunos bl del <user_id> 移除用户"
        
        return True, result

    def _format_blacklist_entries(self, blacklist: List) -> str:
        """格式化黑名单条目
        
        Args:
            blacklist: 黑名单数据列表
            
        Returns:
            str: 格式化后的条目字符串
        """
        entries = []
        for i, (_, user_id, bl_group_id, reason, added_by, created_at) in enumerate(blacklist, 1):
            reason_text = f" - {reason}" if reason else ""
            scope_indicator = " [全局]" if bl_group_id is None else ""
            entries.append(f"{i}. {user_id}{scope_indicator}{reason_text}")
        
        return "\n".join(entries)

    def is_user_blacklisted(self, user_id: str, group_id: str = None) -> bool:
        """检查用户是否在黑名单中
        
        Args:
            user_id: 用户ID
            group_id: 群组ID
            
        Returns:
            bool: 是否在黑名单中
        """
        return self.db.is_in_blacklist(user_id, group_id)

    def get_user_blacklist_info(self, user_id: str, group_id: str = None):
        """获取用户黑名单信息
        
        Args:
            user_id: 用户ID
            group_id: 群组ID
            
        Returns:
            黑名单信息或None
        """
        return self.db.get_user_blacklist_info(user_id, group_id)


class GroupService:
    """群组服务 - 处理群组相关业务逻辑"""
    
    def __init__(self, database: SunosDatabase):
        self.db = database

    def set_group_enabled(self, group_id: str, enabled: bool) -> Tuple[bool, str]:
        """设置群聊开关
        
        Args:
            group_id: 群组ID
            enabled: 是否启用
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        if self.db.set_group_enabled(group_id, enabled):
            status_msg = "✅ 已为当前群聊开启" if enabled else "❌ 已为当前群聊关闭"
            return True, f"{status_msg} SunOS 功能"
        else:
            return False, "设置失败"

    def is_group_enabled(self, group_id: str) -> bool:
        """检查群聊是否启用
        
        Args:
            group_id: 群组ID
            
        Returns:
            bool: 是否启用
        """
        return self.db.is_group_enabled(group_id)

    def get_group_status(
        self, group_id: str, user_permission_text: str, keyword_count: int
    ) -> str:
        """获取群组状态信息
        
        Args:
            group_id: 群组ID
            user_permission_text: 用户权限文本
            keyword_count: 词库数量
            
        Returns:
            str: 状态信息
        """
        is_enabled = self.db.is_group_enabled(group_id)
        status = "✅ 已开启" if is_enabled else "❌ 已关闭"

        welcome_msg = self.db.get_welcome_message(group_id)
        has_welcome = "✅ 已设置" if welcome_msg else "❌ 未设置"

        result = f"""📊 SunOS 功能状态

群聊: {group_id}
功能状态: {status}
词库数量: {keyword_count} 条
欢迎语: {has_welcome}

👤 您的权限: {user_permission_text}"""

        return result