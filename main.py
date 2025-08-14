from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .database import SunosDatabase

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

                result += "\n使用 /sunos ck del <序号> 删除词库"
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
        """自动回复 - 精确匹配关键词并回复"""
        # 跳过指令消息和唤醒消息
        if event.is_at_or_wake_command:
            return
        
        group_id = event.get_group_id()
        
        # 检查群聊是否开启功能
        if group_id and not self.db.is_group_enabled(group_id):
            return
        
        # 精确匹配关键词（完全匹配消息内容）
        message_text = event.message_str.strip()
        keywords = self.db.get_all_keywords()
        
        for _, keyword, reply in keywords:
            if message_text == keyword:  # 精确匹配
                yield event.plain_result(reply)
                break  # 找到匹配后立即停止

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_events(self, event: AstrMessageEvent):
        """处理群聊事件 - 入群欢迎和退群通知"""
        # 跳过普通消息，只处理系统通知
        if event.message_str:  # 如果有文本消息内容，说明是普通消息
            return
            
        # 只处理群聊事件
        group_id = event.get_group_id()
        if not group_id:
            return
        
        # 检查群聊是否开启功能
        if not self.db.is_group_enabled(group_id):
            return
        
        # 获取原始消息数据
        raw_message = event.message_obj.raw_message
        logger.info(f"群事件原始数据: {raw_message}")
        
        # 处理不同类型的群事件
        try:
            # 方式1: 检查字典格式的原始消息
            if isinstance(raw_message, dict):
                notice_type = raw_message.get('notice_type')
                sub_type = raw_message.get('sub_type')
                user_id = raw_message.get('user_id')
                
                # 入群事件
                if notice_type == 'group_increase' and user_id:
                    async for result in self._handle_member_join(event, group_id, str(user_id)):
                        yield result
                # 退群事件  
                elif notice_type == 'group_decrease' and user_id:
                    async for result in self._handle_member_leave(event, group_id, str(user_id), str(sub_type) if sub_type else 'unknown'):
                        yield result
            
            # 方式2: 检查对象属性格式
            elif hasattr(raw_message, 'notice_type'):
                notice_type = getattr(raw_message, 'notice_type', None)
                user_id = getattr(raw_message, 'user_id', None)
                sub_type = getattr(raw_message, 'sub_type', None)
                
                # 入群事件
                if notice_type == 'group_increase' and user_id:
                    async for result in self._handle_member_join(event, group_id, str(user_id)):
                        yield result
                # 退群事件
                elif notice_type == 'group_decrease' and user_id:
                    async for result in self._handle_member_leave(event, group_id, str(user_id), str(sub_type) if sub_type else 'unknown'):
                        yield result
                    
        except Exception as e:
            logger.error(f"处理群事件失败: {e}")

    async def _handle_member_join(self, event: AstrMessageEvent, group_id: str, user_id: str):
        """处理成员入群"""
        if not user_id:
            return
            
        welcome_msg = self.db.get_welcome_message(group_id)
        
        if welcome_msg:
            # 构建消息链，正确处理占位符
            import astrbot.api.message_components as Comp
            chain = []
            
            # 解析欢迎语，替换占位符
            parts = welcome_msg.split("{user}")
            for i, part in enumerate(parts):
                if i > 0:  # 在{user}位置添加At组件
                    chain.append(Comp.At(qq=user_id))
                if part:  # 添加文本部分
                    # 替换{group}占位符
                    text = part.replace("{group}", group_id)
                    chain.append(Comp.Plain(text))
            
            yield event.chain_result(chain)
        else:
            # 默认欢迎语，使用消息链
            import astrbot.api.message_components as Comp
            chain = [
                Comp.At(qq=user_id),
                Comp.Plain(" 欢迎加入群聊！")
            ]
            yield event.chain_result(chain)
        
        logger.info(f"用户 {user_id} 加入了群聊 {group_id}")

    async def _handle_member_leave(self, event: AstrMessageEvent, group_id: str, user_id: str, sub_type: str):
        """处理成员退群"""
        # 根据退群类型记录日志和发送通知
        if sub_type == 'leave':
            logger.info(f"用户 {user_id} 主动离开了群聊 {group_id}")
            yield event.plain_result(f"用户 {user_id} 离开了群聊")
        elif sub_type == 'kick':
            logger.info(f"用户 {user_id} 被踢出了群聊 {group_id}")
            yield event.plain_result(f"用户 {user_id} 被移出了群聊")
        elif sub_type == 'kick_me':
            logger.info(f"机器人被踢出了群聊 {group_id}")
            # 机器人被踢出时无法发送消息
        else:
            logger.info(f"用户 {user_id} 离开了群聊 {group_id} (类型: {sub_type})")
            yield event.plain_result(f"用户 {user_id} 离开了群聊")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("SunOS 插件已卸载")
