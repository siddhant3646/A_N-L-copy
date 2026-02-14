"""
Tests for JS Loader module.
"""

import os
import pytest
from pathlib import Path
from src.sentinel.js_loader import JSLoader, load_js


class TestJSLoaderInit:
    """Test JSLoader initialization."""
    
    def test_init_with_default_path(self):
        """Test initialization with default path."""
        loader = JSLoader()
        assert loader.js_dir is not None
        assert isinstance(loader.js_dir, Path)
    
    def test_init_with_custom_path(self, temp_directory):
        """Test initialization with custom path."""
        custom_path = Path(temp_directory) / "js"
        loader = JSLoader(custom_path)
        assert loader.js_dir == custom_path


class TestJSLoaderLoad:
    """Test loading JavaScript files."""
    
    def test_load_existing_file(self, temp_directory):
        """Test loading an existing JS file."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        # Create test file
        test_file = js_dir / "test.js"
        test_file.write_text("console.log('hello');")
        
        loader = JSLoader(js_dir)
        content = loader.load("test.js")
        
        assert content == "console.log('hello');"
    
    def test_load_caches_result(self, temp_directory):
        """Test that loaded content is cached."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        test_file = js_dir / "cached.js"
        test_file.write_text("var x = 1;")
        
        loader = JSLoader(js_dir)
        
        # Load twice
        content1 = loader.load("cached.js")
        content2 = loader.load("cached.js")
        
        # Should be same object (from cache)
        assert content1 is content2
    
    def test_load_nonexistent_file(self, temp_directory):
        """Test loading non-existent file raises error."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        loader = JSLoader(js_dir)
        
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.js")
    
    def test_load_nested_file(self, temp_directory):
        """Test loading file from subdirectory."""
        js_dir = Path(temp_directory) / "js"
        nested_dir = js_dir / "linkedin"
        nested_dir.mkdir(parents=True)
        
        test_file = nested_dir / "form.js"
        test_file.write_text("// LinkedIn form code")
        
        loader = JSLoader(js_dir)
        content = loader.load("linkedin/form.js")
        
        assert "LinkedIn form code" in content


class TestJSLoaderLoadWithVars:
    """Test loading JS with variable substitution."""
    
    def test_load_with_variables(self, temp_directory):
        """Test loading JS with variable replacement."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        # Create template file
        test_file = js_dir / "template.js"
        test_file.write_text("var timeout = {{ timeout }}; var retries = {{ retries }};")
        
        loader = JSLoader(js_dir)
        content = loader.load_with_vars("template.js", {
            "timeout": "5000",
            "retries": "3"
        })
        
        assert "timeout = 5000" in content
        assert "retries = 3" in content
    
    def test_load_with_missing_vars(self, temp_directory):
        """Test loading with missing variables leaves placeholders."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        test_file = js_dir / "partial.js"
        test_file.write_text("var x = {{ x }}; var y = {{ y }};")
        
        loader = JSLoader(js_dir)
        content = loader.load_with_vars("partial.js", {"x": "1"})
        
        assert "x = 1" in content
        assert "{{ y }}" in content  # Not replaced


class TestJSLoaderClearCache:
    """Test cache clearing."""
    
    def test_clear_cache(self, temp_directory):
        """Test clearing the cache."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        test_file = js_dir / "cached.js"
        test_file.write_text("// content")
        
        loader = JSLoader(js_dir)
        loader.load("cached.js")
        
        # Verify cached
        assert "cached.js" in loader._cache
        
        # Clear cache
        loader.clear_cache()
        
        assert len(loader._cache) == 0


class TestJSLoaderListFiles:
    """Test listing available JS files."""
    
    def test_list_files(self, temp_directory):
        """Test listing all JS files."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        # Create files
        (js_dir / "utils.js").write_text("")
        (js_dir / "helpers.js").write_text("")
        
        nested = js_dir / "linkedin"
        nested.mkdir()
        (nested / "form.js").write_text("")
        
        loader = JSLoader(js_dir)
        files = loader.list_files()
        
        assert "utils.js" in files
        assert "helpers.js" in files
        assert "linkedin/form.js" in files
    
    def test_list_files_in_subdirectory(self, temp_directory):
        """Test listing files in specific subdirectory."""
        js_dir = Path(temp_directory) / "js"
        linkedin_dir = js_dir / "linkedin"
        linkedin_dir.mkdir(parents=True)
        
        (linkedin_dir / "form.js").write_text("")
        (linkedin_dir / "modal.js").write_text("")
        
        loader = JSLoader(js_dir)
        files = loader.list_files("linkedin")
        
        assert "linkedin/form.js" in files or "form.js" in files
        assert "linkedin/modal.js" in files or "modal.js" in files
    
    def test_list_files_empty_directory(self, temp_directory):
        """Test listing files in empty directory."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        loader = JSLoader(js_dir)
        files = loader.list_files()
        
        assert files == []
    
    def test_list_files_nonexistent_subdirectory(self, temp_directory):
        """Test listing files in non-existent subdirectory."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        loader = JSLoader(js_dir)
        files = loader.list_files("nonexistent")
        
        assert files == []


class TestLoadJSFunction:
    """Test load_js convenience function."""
    
    def test_load_js_convenience(self, temp_directory):
        """Test the convenience function."""
        js_dir = Path(temp_directory) / "js"
        js_dir.mkdir()
        
        test_file = js_dir / "test.js"
        test_file.write_text("// test content")
        
        content = load_js("test.js", str(js_dir))
        
        assert content == "// test content"
