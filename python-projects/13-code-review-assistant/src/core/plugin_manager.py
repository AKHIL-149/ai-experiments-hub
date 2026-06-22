"""
Plugin Manager - Handles plugin loading, registration, and execution
"""

import os
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Type, Callable
import logging
import json

from .plugin_base import (
    BasePlugin, AnalyzerPlugin, FormatterPlugin, ReporterPlugin,
    IntegrationPlugin, PluginType, PluginStatus, PluginHook,
    PluginContext, PluginLoadError, PluginExecutionError,
    PluginValidationError
)


logger = logging.getLogger(__name__)


class PluginManager:
    """Manages all plugins"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_dir = Path('./plugins')
        self.plugin_dir.mkdir(parents=True, exist_ok=True)

        # Hook callbacks
        self.hook_callbacks: Dict[PluginHook, List[Callable]] = {
            hook: [] for hook in PluginHook
        }

        self._initialized = True

    def load_plugin_from_file(self, file_path: str) -> Optional[BasePlugin]:
        """
        Load a plugin from a Python file.

        Args:
            file_path: Path to plugin file

        Returns:
            Loaded plugin instance or None

        Raises:
            PluginLoadError: If plugin loading fails
        """
        try:
            # Import module
            spec = importlib.util.spec_from_file_location("plugin_module", file_path)
            if not spec or not spec.loader:
                raise PluginLoadError(f"Cannot load plugin from {file_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules["plugin_module"] = module
            spec.loader.exec_module(module)

            # Find plugin class
            plugin_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type) and
                    issubclass(obj, BasePlugin) and
                    obj != BasePlugin and
                    obj not in [AnalyzerPlugin, FormatterPlugin, ReporterPlugin, IntegrationPlugin]
                ):
                    plugin_class = obj
                    break

            if not plugin_class:
                raise PluginLoadError(f"No plugin class found in {file_path}")

            # Instantiate plugin
            plugin = plugin_class()

            # Validate plugin
            self._validate_plugin(plugin)

            return plugin

        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin from {file_path}: {str(e)}")

    def load_plugin_from_dict(self, config: Dict[str, Any]) -> Optional[BasePlugin]:
        """
        Load a plugin from configuration dictionary.

        Args:
            config: Plugin configuration

        Returns:
            Loaded plugin instance or None
        """
        try:
            plugin_type = config.get('type')
            plugin_module = config.get('module')
            plugin_class_name = config.get('class')

            if not all([plugin_type, plugin_module, plugin_class_name]):
                raise PluginLoadError("Missing required plugin configuration")

            # Import module
            module = importlib.import_module(plugin_module)

            # Get plugin class
            plugin_class = getattr(module, plugin_class_name)

            # Instantiate plugin
            plugin = plugin_class()

            # Validate plugin
            self._validate_plugin(plugin)

            return plugin

        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin from config: {str(e)}")

    def _validate_plugin(self, plugin: BasePlugin):
        """
        Validate a plugin.

        Args:
            plugin: Plugin to validate

        Raises:
            PluginValidationError: If validation fails
        """
        if not isinstance(plugin, BasePlugin):
            raise PluginValidationError("Plugin must inherit from BasePlugin")

        if not plugin.metadata:
            raise PluginValidationError("Plugin must have metadata")

        if not plugin.metadata.name:
            raise PluginValidationError("Plugin must have a name")

        if not plugin.metadata.version:
            raise PluginValidationError("Plugin must have a version")

        # Check for required methods
        if not hasattr(plugin, 'initialize') or not callable(plugin.initialize):
            raise PluginValidationError("Plugin must implement initialize()")

        if not hasattr(plugin, 'shutdown') or not callable(plugin.shutdown):
            raise PluginValidationError("Plugin must implement shutdown()")

    def register_plugin(self, plugin: BasePlugin) -> bool:
        """
        Register a plugin.

        Args:
            plugin: Plugin to register

        Returns:
            True if registration successful
        """
        try:
            plugin_id = plugin.metadata.name

            if plugin_id in self.plugins:
                logger.warning(f"Plugin {plugin_id} already registered, updating...")

            self.plugins[plugin_id] = plugin

            # Register plugin hooks
            for hook, callbacks in plugin.hooks.items():
                for callback in callbacks:
                    self.hook_callbacks[hook].append(callback)

            logger.info(f"Registered plugin: {plugin_id} v{plugin.metadata.version}")
            return True

        except Exception as e:
            logger.error(f"Failed to register plugin: {str(e)}")
            return False

    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if unregistration successful
        """
        try:
            if plugin_id not in self.plugins:
                return False

            plugin = self.plugins[plugin_id]

            # Disable plugin first
            plugin.disable()

            # Remove hook callbacks
            for hook, callbacks in plugin.hooks.items():
                for callback in callbacks:
                    if callback in self.hook_callbacks[hook]:
                        self.hook_callbacks[hook].remove(callback)

            # Remove plugin
            del self.plugins[plugin_id]

            logger.info(f"Unregistered plugin: {plugin_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister plugin {plugin_id}: {str(e)}")
            return False

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """Get a plugin by ID"""
        return self.plugins.get(plugin_id)

    def get_all_plugins(self) -> List[BasePlugin]:
        """Get all registered plugins"""
        return list(self.plugins.values())

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[BasePlugin]:
        """Get plugins by type"""
        return [
            plugin for plugin in self.plugins.values()
            if plugin.metadata.plugin_type == plugin_type
        ]

    def enable_plugin(self, plugin_id: str) -> bool:
        """
        Enable a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if enabled successfully
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return False

        try:
            plugin.enable()
            return plugin.status == PluginStatus.ACTIVE
        except Exception as e:
            logger.error(f"Failed to enable plugin {plugin_id}: {str(e)}")
            plugin.status = PluginStatus.ERROR
            return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """
        Disable a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if disabled successfully
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return False

        try:
            plugin.disable()
            return True
        except Exception as e:
            logger.error(f"Failed to disable plugin {plugin_id}: {str(e)}")
            return False

    def execute_hook(
        self,
        hook: PluginHook,
        context: PluginContext,
        *args,
        **kwargs
    ) -> List[Any]:
        """
        Execute all callbacks for a hook.

        Args:
            hook: Hook to execute
            context: Plugin context
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            List of results from callbacks
        """
        results = []

        callbacks = self.hook_callbacks.get(hook, [])

        for callback in callbacks:
            try:
                result = callback(context, *args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Error executing hook {hook.value}: {str(e)}")
                raise PluginExecutionError(f"Hook execution failed: {str(e)}")

        return results

    def run_analyzers(
        self,
        code: str,
        language: str,
        file_path: str,
        context: PluginContext
    ) -> List[Dict[str, Any]]:
        """
        Run all analyzer plugins on code.

        Args:
            code: Code to analyze
            language: Programming language
            file_path: File path
            context: Plugin context

        Returns:
            List of all issues found by all analyzers
        """
        all_issues = []

        analyzer_plugins = self.get_plugins_by_type(PluginType.ANALYZER)

        for plugin in analyzer_plugins:
            if not plugin.is_enabled():
                continue

            # Check language support
            if (
                plugin.metadata.supported_languages and
                language not in plugin.metadata.supported_languages
            ):
                continue

            try:
                issues = plugin.analyze(code, language, file_path)
                all_issues.extend(issues)
            except Exception as e:
                logger.error(f"Analyzer plugin {plugin.metadata.name} failed: {str(e)}")

        return all_issues

    def load_plugins_from_directory(self, directory: Optional[str] = None) -> int:
        """
        Load all plugins from a directory.

        Args:
            directory: Directory to load from (defaults to self.plugin_dir)

        Returns:
            Number of plugins loaded
        """
        if directory:
            plugin_dir = Path(directory)
        else:
            plugin_dir = self.plugin_dir

        if not plugin_dir.exists():
            return 0

        loaded_count = 0

        for file_path in plugin_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            try:
                plugin = self.load_plugin_from_file(str(file_path))
                if plugin and self.register_plugin(plugin):
                    loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to load plugin from {file_path}: {str(e)}")

        logger.info(f"Loaded {loaded_count} plugins from {plugin_dir}")
        return loaded_count

    def get_plugin_statistics(self) -> Dict[str, Any]:
        """Get plugin statistics"""
        return {
            'total_plugins': len(self.plugins),
            'active_plugins': len([p for p in self.plugins.values() if p.status == PluginStatus.ACTIVE]),
            'inactive_plugins': len([p for p in self.plugins.values() if p.status == PluginStatus.INACTIVE]),
            'error_plugins': len([p for p in self.plugins.values() if p.status == PluginStatus.ERROR]),
            'by_type': {
                plugin_type.value: len(self.get_plugins_by_type(plugin_type))
                for plugin_type in PluginType
            }
        }

    def export_plugin_manifest(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        Export plugin manifest.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin manifest dictionary
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return None

        return {
            'id': plugin_id,
            'metadata': plugin.metadata.to_dict(),
            'status': plugin.status.value,
            'enabled': plugin.is_enabled(),
            'hooks': [hook.value for hook in plugin.hooks.keys()]
        }

    def save_plugin_manifest(self, plugin_id: str, file_path: str) -> bool:
        """
        Save plugin manifest to file.

        Args:
            plugin_id: Plugin ID
            file_path: Output file path

        Returns:
            True if saved successfully
        """
        manifest = self.export_plugin_manifest(plugin_id)
        if not manifest:
            return False

        try:
            with open(file_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save manifest: {str(e)}")
            return False


# Global plugin manager instance
plugin_manager = PluginManager()
