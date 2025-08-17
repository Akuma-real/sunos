# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a SunOS group chat management plugin for AstrBot v2.0, providing keyword management, welcome messages, and auto-reply functionality for QQ groups. The plugin has been completely refactored using modern MVC architecture with dependency injection and now includes OneBot11 API integration for enhanced group management capabilities.

## Development Commands

**Plugin Development Workflow**:
- Deploy to AstrBot plugins directory: `data/plugins/sunos/`
- Use VSCode to edit plugin files
- Reload plugin via AstrBot WebUI: Plugin Management → Manage → Reload Plugin
- Database auto-creates at `data/sunos_plugin.db`

**Code Formatting** (required before commits):
```bash
ruff format .  # Format code with ruff tool
```

**OneBot11 Integration Tests**:
```bash
# 在AstrBot环境中测试adapter配置
# 需要在AstrBot插件加载后运行，非独立环境命令
# python -c "from core import create_onebot_adapter; print('OneBot11 ready')"
```

**Test Commands**:
```bash
# Basic functionality
/sunos help
/sunos ck list
/sunos status

# Admin functions (requires admin role in AstrBot)
/sunos enable
/sunos ck add test "Test reply"
/sunos wc set "Welcome {user} to group {group}!"
```

## Architecture v2.0

### Modern MVC Architecture

**Layer Structure**:
```
main.py (Star Plugin Class)
    ↓ (Service Integration)
core/services.py (Business Logic)
    ↓ (Data Access)
core/database.py (Data Access Layer)
    ↓ (Database Operations)
core/utils.py (Helper Functions)
core/handlers.py (Event Processing)
core/permissions.py (Authorization)
core/platform.py (Platform Abstraction)
```

**Component Responsibilities**:
- **SunosDatabase**: Direct database operations with table management
- **Services**: Business logic with database integration (KeywordService, WelcomeService, etc.)
- **Handlers**: Event processing and auto-reply logic (GroupEventHandler, AutoReplyHandler)
- **Permissions**: Authorization and access control decorators
- **Platform**: Cross-platform adapter for different messaging systems
- **Utils**: Helper functions (message building, validation, notification management)

### Dependency Injection Container

**Service Initialization** (`main.py:93-119`):
```python
# 初始化核心组件
self.db = SunosDatabase()
self.platform_adapter = PlatformAdapter(context)
self.notification_manager = NotificationManager(cooldown=30)

# 初始化服务层
self.keyword_service = KeywordService(self.db)
self.welcome_service = WelcomeService(self.db)
self.blacklist_service = BlacklistService(self.db)
self.group_service = GroupService(self.db)

# 初始化事件处理器
self.group_event_handler = GroupEventHandler(
    self.blacklist_service, self.welcome_service,
    self.platform_adapter, self.notification_manager
)
self.auto_reply_handler = AutoReplyHandler(
    self.keyword_service, self.group_service
)
```

**Benefits**:
- **Service Integration**: Direct database access through service layer
- **Event-Driven**: Specialized handlers for different event types
- **Modular Design**: Clear separation between data, business logic, and presentation
- **Maintainability**: Well-defined component boundaries reduce complexity

### Decorator System

**Available Decorators**:
```python
from .permissions import admin_required, group_only

@admin_required                              # Permission checking
@group_only                                  # Group chat validation  
async def handler(self, event):              # Method with decorators
    # Handler logic with validation/permissions handled automatically
```

**Cross-Cutting Concerns**:
- **Permission Management**: Automatic admin/group validation
- **Authorization**: Role-based access control for sensitive operations
- **Error Handling**: Unified exception handling with user-friendly messages

### Service Layer Features

**Business Logic Separation**:
- **KeywordService**: Keyword CRUD with duplicate detection
- **WelcomeService**: Template-based welcome message management
- **GroupService**: Feature toggle with status tracking
- **BlacklistService**: User blacklist management with validation

### Service Layer Architecture

**Business Service Classes**:
```python
# Service classes handle business logic with database integration
class KeywordService:
    def __init__(self, db: SunosDatabase):
        self.db = db
    
    def add_keyword(self, keyword: str, reply: str) -> Tuple[bool, str]:
        # Business logic with validation and database operations
```

**Service Features**:
- **Database Integration**: Direct access to SunosDatabase for data operations
- **Business Logic**: Validation, processing, and error handling
- **Return Patterns**: Consistent (success: bool, message: str) return format
- **Error Handling**: Comprehensive validation and user-friendly error messages

### Template System

**Simple Placeholder Engine** (`core/utils.py:MessageBuilder`):
```python
# Supported Placeholders
{user}   # Replaced with @user component
{group}  # Replaced with group ID

# Usage Example
welcome_msg = "Welcome {user} to group {group}!"
chain = MessageBuilder.build_welcome_chain(welcome_msg, user_id, group_id)
```

**Template Features**:
- **Basic Substitution**: Simple placeholder replacement for user and group
- **Component Integration**: Automatic @user component generation
- **Message Chain Building**: Integration with AstrBot message component system

### AstrBot Core Architecture

**"Onion Model" Pipeline**: AstrBot processes messages through nested stages
1. **EventBus**: Async queue receives events from platform adapters
2. **PipelineScheduler**: Executes stages in onion pattern (enter → process → exit)
3. **Stage Flow**: `WakingStage → PluginStage → LLMStage → ResponseStage`
4. **Async Generators**: Each stage can `yield` to pause and resume processing

**Component Hierarchy**:
- **ProviderManager**: LLM supplier management
- **PlatformManager**: Message platform adapters (QQ, Telegram, etc)
- **PluginManager**: Plugin loading and execution
- **ConversationManager**: Session and dialogue tracking
- **EventBus**: Central message dispatch system

### AstrMessageEvent System

**Core Event Object** (`event: AstrMessageEvent`):
- **Message Data**: `event.message_str` (plain text), `event.message_obj` (rich components)
- **Session Info**: `event.unified_msg_origin` (unique session ID), `event.session_id`
- **User Context**: `event.role` ("admin"/"member"), `event.get_sender_id()`, `event.get_group_id()`
- **Platform Info**: `event.get_platform_name()`, `event.platform_meta`

**Event Control Methods**:
- `event.stop_event()` - Halt further processing stages
- `event.continue_event()` - Resume processing
- `event.should_call_llm(False)` - Skip default LLM stage
- `event.set_extra(key, value)` / `event.get_extra(key)` - Cross-stage data

**Response Generation**:
- `yield event.plain_result(text)` - Text response
- `yield event.chain_result([Comp.Plain(), Comp.At()])` - Rich message chain
- `yield event.image_result(path_or_url)` - Image response
- `await event.send(message_chain)` - Direct send (no yield)

### Plugin Framework (Star Class)

**Plugin Base Class** (`main.py:20`):
- Inherit from `Star` base class: `class SunosPlugin(Star)`
- **Required**: `@register(name, author, desc, version, repo)` decorator
- **Required**: `async def terminate(self)` method for cleanup
- Access AstrBot via `self.context: Context`

**Event Handlers with Filters**:
```python
@filter.command("commandname")                    # Command: /commandname
@filter.command_group("group")                    # Command group: /group subcommand
@filter.event_message_type(EventMessageType.ALL) # All messages
@filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP) # Platform-specific
@filter.permission_type(PermissionType.ADMIN)    # Admin-only
```

**Context API** (`self.context`):
- `get_using_provider()` - Current LLM provider
- `get_llm_tool_manager()` - Function calling tools
- `get_config()` - AstrBot configuration
- `send_message(session_id, message_chain)` - Active messaging
- `get_registered_star(name)` - Other plugin instances

### Database Architecture

**Modern Repository Pattern**:
- **BaseRepository**: Abstract interface with transaction management
- **Concrete Repositories**: Keyword, Welcome, Group repositories
- **Connection Pooling**: Efficient database connection management
- **Transaction Safety**: Automatic rollback on errors

**Legacy Compatibility**:
- **SunosDatabase**: Original database class maintained for compatibility
- **Migration Path**: New services can gradually replace legacy methods
- **Dual Access**: Both new repositories and legacy database available

## Development Guidelines

### Modern Development Patterns

**Repository Pattern Usage**:
```python
# Service layer uses repositories for data access
class KeywordService:
    def __init__(self, repo: KeywordRepository, cache: CacheService):
        self.repo = repo        # Data access abstraction
        self.cache = cache      # Cache management
    
    def add_keyword(self, keyword: str, reply: str) -> Tuple[bool, str]:
        # Business logic with caching integration
```

**Decorator-Based Validation**:
```python
@admin_required                 # Automatic permission checking
@validate_params(min_count=2)   # Parameter count validation
async def _handle_add(self, event: AstrMessageEvent, params: List[str]):
    # Clean handler logic without boilerplate validation
```

**Error Handling Strategy**:
```python
@error_handler_decorator("主命令处理")  # Automatic exception handling
async def sunos_main(self, event: AstrMessageEvent):
    # Business logic with automatic error recovery
```

### Performance Optimizations

**Caching Strategy**:
- **Method-Level Caching**: Frequently accessed data cached automatically
- **Cache Invalidation**: Smart cache clearing on data mutations
- **Statistics Tracking**: Monitor cache hit rates for optimization
- **TTL Configuration**: Configurable expiration times per use case

**Database Optimizations**:
- **Connection Pooling**: Reuse database connections efficiently
- **Batch Operations**: Multiple operations in single transaction
- **Index Usage**: Proper indexing for query performance
- **Query Optimization**: Prepared statements and efficient queries

### Testing and Quality Assurance

**Code Quality Tools**:
- **Type Checking**: Full mypy compatibility with type hints
- **Code Formatting**: ruff for consistent code style
- **Import Sorting**: Organized imports with proper dependencies
- **Documentation**: Comprehensive docstrings with parameter types

**Testing Strategy**:
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test service layer interactions
- **Mock Dependencies**: Easy testing with dependency injection
- **Error Case Testing**: Comprehensive error handling validation

### Migration Strategy

**Legacy Compatibility**:
- **Backward Compatibility**: Old database methods still work
- **Gradual Migration**: New features use modern architecture
- **Dual Support**: Both old and new APIs available during transition
- **Documentation**: Clear migration path for existing code

**Future Enhancements**:
- **Plugin Hot Reload**: Runtime configuration updates
- **Multi-Language Support**: Internationalization framework
- **Advanced Templating**: More sophisticated template features
- **Monitoring Integration**: Performance metrics and health checks

## Core Development Patterns

**Async Generator Pattern**:
```python
async def handler(self, event: AstrMessageEvent):
    yield event.plain_result("First response")
    # Can yield multiple responses
    yield event.image_result("path/to/image.jpg")
```

**Modern Message Chain Construction**:
```python
import astrbot.api.message_components as Comp
from .utils import MessageBuilder

# Template-based message building
welcome_msg = "Welcome {user} to {group}!"
chain = MessageBuilder.build_welcome_chain(welcome_msg, user_id, group_id)

# Rich message chain construction  
chain = [
    Comp.At(qq=user_id),
    Comp.Plain(" 欢迎加入群聊！")
]
yield event.chain_result(chain)
```

**Service Layer Integration**:
```python
# Clean business logic with automatic caching
result = self.keyword_service.find_keyword_reply(message_text)
if result:
    yield event.plain_result(result)
```