"""File operations tool for reading, writing, and transforming files."""

import json
import csv
from pathlib import Path
from typing import Dict, Any
from .base_tool import BaseTool


class FileOpsTool(BaseTool):
    """Tool for file operations: read, write, append, and transform files."""

    @property
    def name(self) -> str:
        return "file_operations"

    @property
    def description(self) -> str:
        return """Read, write, or transform files (TXT, JSON, CSV).
        Operations:
        - read: Read file content
        - write: Write content to file
        - append: Append content to file
        - transform: Convert between formats (csv->json, json->csv)"""

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "append", "transform"],
                    "description": "Type of file operation"
                },
                "path": {
                    "type": "string",
                    "description": "File path (relative to project root)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write/append (required for write/append operations)"
                },
                "target_format": {
                    "type": "string",
                    "enum": ["json", "csv"],
                    "description": "Target format for transform operation"
                }
            },
            "required": ["operation", "path"]
        }

    def execute(self, operation: str, path: str, content: str = None, target_format: str = None) -> Dict[str, Any]:
        """Execute file operation."""
        try:
            file_path = Path(path)

            if operation == "read":
                return self._read_file(file_path)

            elif operation == "write":
                if content is None:
                    raise ValueError("Content is required for write operation")
                return self._write_file(file_path, content)

            elif operation == "append":
                if content is None:
                    raise ValueError("Content is required for append operation")
                return self._append_file(file_path, content)

            elif operation == "transform":
                if target_format is None:
                    raise ValueError("target_format is required for transform operation")
                return self._transform_file(file_path, target_format)

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "path": path
            }

    def _read_file(self, file_path: Path) -> Dict[str, Any]:
        """Read file content."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = file_path.read_text(encoding='utf-8')

        return {
            "success": True,
            "operation": "read",
            "path": str(file_path),
            "content": content,
            "size": len(content)
        }

    def _write_file(self, file_path: Path, content: str) -> Dict[str, Any]:
        """Write content to file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        return {
            "success": True,
            "operation": "write",
            "path": str(file_path),
            "size": len(content)
        }

    def _append_file(self, file_path: Path, content: str) -> Dict[str, Any]:
        """Append content to file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "operation": "append",
            "path": str(file_path),
            "appended_size": len(content)
        }

    def _transform_file(self, file_path: Path, target_format: str) -> Dict[str, Any]:
        """Transform file format."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        source_format = file_path.suffix.lstrip('.')

        if source_format == "csv" and target_format == "json":
            return self._csv_to_json(file_path)
        elif source_format == "json" and target_format == "csv":
            return self._json_to_csv(file_path)
        else:
            raise ValueError(f"Unsupported transformation: {source_format} -> {target_format}")

    def _csv_to_json(self, csv_path: Path) -> Dict[str, Any]:
        """Convert CSV to JSON."""
        data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        output_path = csv_path.with_suffix('.json')
        output_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

        return {
            "success": True,
            "operation": "transform",
            "source": str(csv_path),
            "target": str(output_path),
            "format": "csv->json",
            "records": len(data)
        }

    def _json_to_csv(self, json_path: Path) -> Dict[str, Any]:
        """Convert JSON to CSV."""
        data = json.loads(json_path.read_text(encoding='utf-8'))

        if not isinstance(data, list):
            raise ValueError("JSON must be a list of objects for CSV conversion")

        if not data:
            raise ValueError("JSON list is empty")

        output_path = json_path.with_suffix('.csv')

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if data:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

        return {
            "success": True,
            "operation": "transform",
            "source": str(json_path),
            "target": str(output_path),
            "format": "json->csv",
            "records": len(data)
        }
