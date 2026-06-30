"""
Tests for ProfileManager module.
"""

import os
from src.sentinel.profile_manager import ProfileManager


class TestProfileManagerInit:
    """Test ProfileManager initialization."""
    
    def test_init_with_default_path(self):
        """Test initialization with default path."""
        pm = ProfileManager()
        assert pm.profile_dir.name == "p"
        assert pm.cleanup_count == 0
    
    def test_init_with_custom_path(self, temp_directory):
        """Test initialization with custom path."""
        custom_path = os.path.join(temp_directory, "custom_profile")
        pm = ProfileManager(custom_path)
        assert str(pm.profile_dir) == custom_path


class TestProfileManagerCleanup:
    """Test profile cleanup functionality."""
    
    def test_cleanup_nonexistent_directory(self, temp_directory):
        """Test cleanup when directory doesn't exist."""
        pm = ProfileManager(os.path.join(temp_directory, "nonexistent"))
        result = pm.cleanup()
        assert result is True
    
    def test_cleanup_existing_directory(self, temp_directory):
        """Test cleanup removes existing directory."""
        profile_path = os.path.join(temp_directory, "test_profile")
        os.makedirs(profile_path)
        
        # Create a test file
        with open(os.path.join(profile_path, "test.txt"), "w") as f:
            f.write("test content")
        
        pm = ProfileManager(profile_path)
        result = pm.cleanup()
        
        assert result is True
        assert not os.path.exists(profile_path)
        assert pm.cleanup_count == 1
    
    def test_cleanup_increments_counter(self, temp_directory):
        """Test that cleanup increments counter."""
        profile_path = os.path.join(temp_directory, "test_profile")
        os.makedirs(profile_path)
        
        pm = ProfileManager(profile_path)
        pm.cleanup()
        
        # Recreate directory for second cleanup
        os.makedirs(profile_path)
        pm.cleanup()
        
        assert pm.cleanup_count == 2


class TestProfileManagerEnsureFresh:
    """Test ensure_fresh functionality."""
    
    def test_ensure_fresh_creates_directory(self, temp_directory):
        """Test ensure_fresh creates fresh directory."""
        profile_path = os.path.join(temp_directory, "fresh_profile")
        pm = ProfileManager(profile_path)
        
        result = pm.ensure_fresh()
        
        assert result == profile_path
        assert os.path.exists(profile_path)
        assert os.path.isdir(profile_path)
    
    def test_ensure_fresh_removes_existing(self, temp_directory):
        """Test ensure_fresh removes existing directory first."""
        profile_path = os.path.join(temp_directory, "existing_profile")
        os.makedirs(profile_path)
        
        # Create old file
        old_file = os.path.join(profile_path, "old.txt")
        with open(old_file, "w") as f:
            f.write("old content")
        
        pm = ProfileManager(profile_path)
        pm.ensure_fresh()
        
        # Old file should be gone
        assert not os.path.exists(old_file)
        assert os.path.exists(profile_path)


class TestProfileManagerPresence:
    """Test profile presence checks."""
    
    def test_is_profile_present_true(self, temp_directory):
        """Test detection of existing profile."""
        profile_path = os.path.join(temp_directory, "present_profile")
        os.makedirs(profile_path)
        
        pm = ProfileManager(profile_path)
        assert pm.is_profile_present() is True
    
    def test_is_profile_present_false(self, temp_directory):
        """Test detection of non-existing profile."""
        profile_path = os.path.join(temp_directory, "missing_profile")
        pm = ProfileManager(profile_path)
        assert pm.is_profile_present() is False


class TestProfileManagerSize:
    """Test profile size calculation."""
    
    def test_get_profile_size_empty(self, temp_directory):
        """Test size of empty profile."""
        profile_path = os.path.join(temp_directory, "empty_profile")
        os.makedirs(profile_path)
        
        pm = ProfileManager(profile_path)
        assert pm.get_profile_size() == 0
        assert pm.get_profile_size_mb() == 0.0
    
    def test_get_profile_size_with_files(self, temp_directory):
        """Test size calculation with files."""
        profile_path = os.path.join(temp_directory, "sized_profile")
        os.makedirs(profile_path)
        
        # Create files with known content
        content = "x" * 1000  # 1000 bytes
        with open(os.path.join(profile_path, "file1.txt"), "w") as f:
            f.write(content)
        with open(os.path.join(profile_path, "file2.txt"), "w") as f:
            f.write(content)
        
        pm = ProfileManager(profile_path)
        size = pm.get_profile_size()
        
        # Should be approximately 2000 bytes (allowing for filesystem overhead)
        assert size >= 2000
        assert pm.get_profile_size_mb() >= 0.001


class TestProfileManagerStaticMethods:
    """Test static convenience methods."""
    
    def test_cleanup_static(self, temp_directory):
        """Test static cleanup method."""
        profile_path = os.path.join(temp_directory, "static_profile")
        os.makedirs(profile_path)
        
        result = ProfileManager.cleanup_static(profile_path)
        
        assert result is True
        assert not os.path.exists(profile_path)
    
    def test_ensure_fresh_static(self, temp_directory):
        """Test static ensure_fresh method."""
        profile_path = os.path.join(temp_directory, "static_fresh")
        
        result = ProfileManager.ensure_fresh_static(profile_path)
        
        assert result == profile_path
        assert os.path.exists(profile_path)


class TestProfileManagerEdgeCases:
    """Test edge cases and error handling."""
    
    def test_cleanup_permission_error(self, temp_directory):
        """Test cleanup handles permission errors gracefully."""
        profile_path = os.path.join(temp_directory, "protected_profile")
        os.makedirs(profile_path)
        
        # Mock shutil.rmtree in the profile_manager module to raise PermissionError
        def mock_rmtree(*args, **kwargs):
            raise PermissionError("Access denied")
        
        import src.sentinel.profile_manager as pm_module
        original_rmtree = pm_module.shutil.rmtree
        pm_module.shutil.rmtree = mock_rmtree
        
        try:
            pm = ProfileManager(profile_path)
            result = pm.cleanup()
            
            # Should return False but not raise exception
            assert result is False
        finally:
            # Restore original rmtree
            pm_module.shutil.rmtree = original_rmtree
    
    def test_get_size_with_nested_directories(self, temp_directory):
        """Test size calculation with nested directories."""
        profile_path = os.path.join(temp_directory, "nested_profile")
        nested_path = os.path.join(profile_path, "subdir", "deep")
        os.makedirs(nested_path)
        
        # Create files at different levels
        with open(os.path.join(profile_path, "root.txt"), "w") as f:
            f.write("x" * 500)
        with open(os.path.join(nested_path, "deep.txt"), "w") as f:
            f.write("x" * 500)
        
        pm = ProfileManager(profile_path)
        size = pm.get_profile_size()
        
        assert size >= 1000
