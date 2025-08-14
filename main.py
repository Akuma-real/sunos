from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.platform import MessageType
import astrbot.api.message_components as Comp
from .database import SunosDatabase
import re

@register("sunos", "Akuma", "SunOS 群聊管理插件 - 词库管理、欢迎语、自动回复", "1.0.0", "https://github.com/AstrBotDevs/AstrBot")
class SunosPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.db = SunosDatabase()
        logger.info("SunOS 插件初始化完成")

    @filter.command("sunos")
    async def sunos_main(self, event: AstrMessageEvent):
        """SunOS 群聊管理插件主命令"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()
        
        if len(message_parts) < 2:
            help_text = """SunOS 群聊管理插件帮助

📚 词库管理 (ck):
/sunos ck add <关键词> <回复内容> - 添加词库
/sunos ck del <序号> - 删除词库
/sunos ck list - 查看词库列表
/sunos ck help - 词库帮助

👋 欢迎语管理 (wc):
/sunos wc set <欢迎语> - 设置欢迎语
/sunos wc del - 删除欢迎语
/sunos wc show - 查看欢迎语
/sunos wc help - 欢迎语帮助

⚙️ 群聊开关:
/sunos enable - 开启功能
/sunos disable - 关闭功能
/sunos status - 查看状态

占位符说明:
{user} - @ 新成员
{group} - 群号"""
            yield event.plain_result(help_text)
            return

        action = message_parts[1]
        
        # 词库管理
        if action == "ck":
            if len(message_parts) < 3:
                yield event.plain_result("用法: /sunos ck <add|del|list|help>")
                return
                
            subaction = message_parts[2]
            
            if subaction == "add":
                if event.role != "admin":
                    yield event.plain_result("此操作需要管理员权限")
                    return
                if len(message_parts) < 5:
                    yield event.plain_result("用法: /sunos ck add <关键词> <回复内容>")
                    return
                
                keyword = message_parts[3]
                reply = " ".join(message_parts[4:])
                reply = reply.replace("\\n", "\n")  # 支持换行符
                
                if self.db.add_keyword(keyword, reply):
                    yield event.plain_result(f"成功添加词库:\n关键词: {keyword}\n回复: {reply}")
                else:
                    yield event.plain_result(f"关键词 '{keyword}' 已存在！")
                    
            elif subaction == "del":
                if event.role != "admin":
                    yield event.plain_result("此操作需要管理员权限")
                    return
                if len(message_parts) < 4:
                    yield event.plain_result("用法: /sunos ck del <序号>")
                    return
                
                try:
                    index = int(message_parts[3])
                except ValueError:
                    yield event.plain_result("序号必须是数字")
                    return
                
                keywords = self.db.get_all_keywords()
                
                if not keywords:
                    yield event.plain_result("当前没有词库条目")
                    return
                
                if index < 1 or index > len(keywords):
                    yield event.plain_result(f"序号错误，请输入 1-{len(keywords)} 之间的数字")
                    return
                
                keyword_data = keywords[index - 1]
                if self.db.delete_keyword(keyword_data[0]):  # keyword_data[0] 是 id
                    yield event.plain_result(f"成功删除词库: {keyword_data[1]}")
                else:
                    yield event.plain_result("删除失败")
                    
            elif subaction == "list":
                keywords = self.db.get_all_keywords()
                
                if not keywords:
                    yield event.plain_result("当前没有词库条目")
                    return
                
                result = f"📚 词库列表 (共 {len(keywords)} 条):\n\n"
                for i, (_, keyword, reply) in enumerate(keywords, 1):
                    # 限制显示长度
                    display_reply = reply[:50] + "..." if len(reply) > 50 else reply
                    display_reply = display_reply.replace("\n", "\\n")
                    result += f"{i}. {keyword} → {display_reply}\n"
                
                result += f"\n使用 /sunos ck del <序号> 删除词库"
                yield event.plain_result(result)
                
            elif subaction == "help":
                help_text = """📚 词库管理帮助

管理员功能:
/sunos ck add <关键词> <回复内容> - 添加词库
/sunos ck del <序号> - 删除词库

用户功能:
/sunos ck list - 查看词库列表
/sunos ck help - 显示此帮助

说明:
- 支持换行符 \\n
- 自动检查重复关键词"""
                yield event.plain_result(help_text)
            else:
                yield event.plain_result("未知操作，使用 /sunos ck help 查看帮助")

        # 欢迎语管理
        elif action == "wc":
            if len(message_parts) < 3:
                yield event.plain_result("用法: /sunos wc <set|del|show|help>")
                return
                
            subaction = message_parts[2]

            if subaction == "set":
                if event.role != "admin":
                    yield event.plain_result("此操作需要管理员权限")
                    return
                if len(message_parts) < 4:
                    yield event.plain_result("用法: /sunos wc set <欢迎语内容>")
                    return
                
                welcome_msg = " ".join(message_parts[3:])
                welcome_msg = welcome_msg.replace("\\n", "\n")  # 支持换行符
                group_id = event.get_group_id()
                
                if not group_id:
                    yield event.plain_result("欢迎语功能仅支持群聊")
                    return
                
                if self.db.set_welcome_message(group_id, welcome_msg):
                    yield event.plain_result(f"成功设置欢迎语:\n{welcome_msg}")
                else:
                    yield event.plain_result("设置欢迎语失败")
                    
            elif subaction == "del":
                if event.role != "admin":
                    yield event.plain_result("此操作需要管理员权限")
                    return
                group_id = event.get_group_id()
                
                if not group_id:
                    yield event.plain_result("欢迎语功能仅支持群聊")
                    return
                
                if self.db.delete_welcome_message(group_id):
                    yield event.plain_result("成功删除当前群的欢迎语设置")
                else:
                    yield event.plain_result("删除失败或当前群未设置欢迎语")
                    
            elif subaction == "show":
                group_id = event.get_group_id()
                
                if not group_id:
                    yield event.plain_result("欢迎语功能仅支持群聊")
                    return
                
                welcome_msg = self.db.get_welcome_message(group_id)
                if welcome_msg:
                    yield event.plain_result(f"当前群欢迎语:\n{welcome_msg}")
                else:
                    yield event.plain_result("当前群未设置欢迎语")
                    
            elif subaction == "help":
                help_text = """👋 欢迎语管理帮助

管理员功能:
/sunos wc set <欢迎语内容> - 设置欢迎语
/sunos wc del - 删除欢迎语

用户功能:
/sunos wc show - 查看欢迎语
/sunos wc help - 显示此帮助

占位符:
{user} - @ 新成员
{group} - 群号

说明:
- 支持换行符 \\n
- 仅支持群聊使用"""
                yield event.plain_result(help_text)
            else:
                yield event.plain_result("未知操作，使用 /sunos wc help 查看帮助")

        # 群聊开关管理
        elif action == "enable":
            if event.role != "admin":
                yield event.plain_result("此操作需要管理员权限")
                return
                
            group_id = event.get_group_id()
            
            if not group_id:
                yield event.plain_result("群聊开关功能仅支持群聊")
                return
            
            if self.db.set_group_enabled(group_id, True):
                yield event.plain_result("✅ 已为当前群聊开启 SunOS 功能")
            else:
                yield event.plain_result("设置失败")

        elif action == "disable":
            if event.role != "admin":
                yield event.plain_result("此操作需要管理员权限")
                return
                
            group_id = event.get_group_id()
            
            if not group_id:
                yield event.plain_result("群聊开关功能仅支持群聊")
                return
            
            if self.db.set_group_enabled(group_id, False):
                yield event.plain_result("❌ 已为当前群聊关闭 SunOS 功能")
            else:
                yield event.plain_result("设置失败")

        elif action == "status":
            group_id = event.get_group_id()
            
            if not group_id:
                yield event.plain_result("群聊开关功能仅支持群聊")
                return
            
            is_enabled = self.db.is_group_enabled(group_id)
            status = "✅ 已开启" if is_enabled else "❌ 已关闭"
            
            # 统计信息
            keywords_count = len(self.db.get_all_keywords())
            welcome_msg = self.db.get_welcome_message(group_id)
            has_welcome = "✅ 已设置" if welcome_msg else "❌ 未设置"
            
            result = f"""📊 SunOS 功能状态

群聊: {group_id}
功能状态: {status}
词库数量: {keywords_count} 条
欢迎语: {has_welcome}"""
            
            yield event.plain_result(result)

        elif action == "help":
            help_text = """SunOS 群聊管理插件帮助

📚 词库管理 (ck):
/sunos ck add <关键词> <回复内容> - 添加词库
/sunos ck del <序号> - 删除词库
/sunos ck list - 查看词库列表
/sunos ck help - 词库帮助

👋 欢迎语管理 (wc):
/sunos wc set <欢迎语> - 设置欢迎语
/sunos wc del - 删除欢迎语
/sunos wc show - 查看欢迎语
/sunos wc help - 欢迎语帮助

⚙️ 群聊开关:
/sunos enable - 开启功能
/sunos disable - 关闭功能
/sunos status - 查看状态

占位符说明:
{user} - @ 新成员
{group} - 群号"""
            yield event.plain_result(help_text)

        else:
            yield event.plain_result("未知操作，使用 /sunos help 查看帮助")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_reply(self, event: AstrMessageEvent):
        """自动回复 - 检测消息中的关键词并回复"""
        # 跳过指令消息
        if event.message_str.startswith('/'):
            return
        
        group_id = event.get_group_id()
        
        # 检查群聊是否开启功能
        if group_id and not self.db.is_group_enabled(group_id):
            return
        
        # 检查关键词匹配
        reply = self.db.find_keyword_reply(event.message_str)
        if reply:
            yield event.plain_result(reply)

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("SunOS 插件已卸载")