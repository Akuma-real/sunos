# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a SunOS group chat management plugin for AstrBot v2.0, providing keyword management, welcome messages, and auto-reply functionality for QQ groups. The plugin has been completely refactored using modern MVC architecture with dependency injection.

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

# Cache management
/sunos cache stats
/sunos cache clear
```

## Architecture v2.0

### Modern MVC Architecture

**Layer Structure**:
```
main.py (Star Plugin Class)
    ↓ (Dependency Injection)
controllers/ (Request Handling)
    ↓ (Business Logic Delegation) 
services/ (Business Logic)
    ↓ (Data Access)
repositories/ (Data Access Layer)
    ↓ (Database Operations)
models/ (Data Models)
```

**Component Responsibilities**:
- **Models**: Data structures with validation and serialization
- **Repositories**: Abstract data access with Repository pattern
- **Services**: Business logic with caching integration
- **Controllers**: Request handling with unified error management
- **Decorators**: Cross-cutting concerns (permissions, validation, caching)
- **Utils**: Helper functions (message building, template parsing, error handling)

### Dependency Injection Container

**Service Initialization** (`main.py:39-77`):
```python
# Repository Layer
self.keyword_repo = KeywordRepository()
self.welcome_repo = WelcomeRepository()
self.group_repo = GroupRepository()

# Service Layer with Cache Integration
self.cache_service = CacheService()
self.keyword_service = KeywordService(self.keyword_repo, self.cache_service)

# Controller Layer with Service Dependencies
self.keyword_controller = KeywordController(self.keyword_service)
```

**Benefits**:
- **Loose Coupling**: Components depend on abstractions, not concrete implementations
- **Testability**: Easy to mock dependencies for unit testing
- **Extensibility**: New features can be added without modifying existing code
- **Maintainability**: Clear separation of concerns reduces complexity

### Decorator System

**Available Decorators**:
```python
from .decorators import admin_required, group_only, validate_params, cached

@admin_required                              # Permission checking
@group_only                                  # Group chat validation  
@validate_params(min_count=2)               # Parameter validation
@cached(ttl=60)                             # Response caching
async def handler(self, event, params):      # Method with decorators
    # Handler logic with validation/permissions handled automatically
```

**Cross-Cutting Concerns**:
- **Permission Management**: Automatic admin/group validation
- **Parameter Validation**: Type checking and count validation
- **Caching**: LRU cache with TTL support and statistics
- **Error Handling**: Unified exception handling with user-friendly messages

### Service Layer Features

**Caching Integration**:
- **LRU Cache**: Least Recently Used eviction strategy
- **TTL Support**: Time-based cache expiration
- **Hit Rate Tracking**: Performance monitoring with statistics
- **Cache Invalidation**: Automatic cache clearing on data updates

**Business Logic Separation**:
- **KeywordService**: Keyword CRUD with duplicate detection
- **WelcomeService**: Template-based welcome message management
- **GroupService**: Feature toggle with status tracking
- **CacheService**: Centralized cache management

### Data Model System

**Type-Safe Models**:
```python
@dataclass
class Keyword:
    id: Optional[int] = None
    keyword: str = ""
    reply: str = ""
    created_at: Optional[datetime] = None
    
    def validate(self) -> Tuple[bool, str]:
        # Validation logic with detailed error messages
```

**Model Features**:
- **Data Validation**: Business rule enforcement
- **Serialization**: JSON conversion for API responses  
- **Type Hints**: Full type safety with mypy compatibility
- **Immutability**: Dataclass with controlled mutation

### Template System

**Advanced Template Engine** (`utils/template_parser.py`):
```python
# Built-in Variables
{date}        # Current date
{time}        # Current time  
{user_id}     # Message sender ID
{group_id}    # Group chat ID
{random:1:10} # Random number between 1-10

# Custom Context Variables
parse_template("Welcome {user_name}!", {"user_name": "Alice"}, event)
```

**Template Features**:
- **Variable Substitution**: Context-aware placeholder replacement
- **Built-in Functions**: Date/time, random numbers, user info
- **Format Modifiers**: `{text:upper}`, `{text:len:10}`, `{text:pad:5:0}`
- **Validation**: Template syntax checking with error reporting

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
from .utils import parse_template

# Template-based message building
template = "Welcome {user} to {group}!"
context = {"group": group_id}
processed = parse_template(template, context, event)

# Rich message chain
chain = [
    Comp.At(qq=user_id),
    Comp.Plain(processed)
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