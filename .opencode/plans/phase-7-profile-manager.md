# Phase 7: Create ProfileManager

## Objective
Implement automatic profile folder cleanup after every cycle.

## Current State
- Profile folder is copied to local `p/` folder at cycle start
- Profile persists across cycles
- Can cause disk space issues and stale sessions

## Implementation Steps

### 7.1 Create ProfileManager Class
**File**: `src/sentinel/profile_manager.py`

**Class Structure**:
```python
class ProfileManager:
    """Manages browser profile folder lifecycle"""
    
    PROFILE_DIR = os.path.join(os.getcwd(), "p")
    
    @classmethod
    def cleanup(cls) -> bool
        """Delete profile folder after cycle completion"""
    
    @classmethod
    def ensure_fresh(cls) -> str
        """Ensure fresh profile folder at cycle start"""
    
    @classmethod
    def is_profile_present(cls) -> bool
        """Check if profile folder exists"""
    
    @classmethod
    def get_profile_size(cls) -> int
        """Get profile folder size in bytes"""
```

### 7.2 Update run.py
**File**: `src/sentinel/run.py`

**Changes**:
```python
async def main():
    cycle_count = 0
    
    while True:
        cycle_count += 1
        
        # FRESH START: Clean profile at cycle start
        ProfileManager.ensure_fresh()
        
        try:
            for task in tasks:
                # ... run tasks
                pass
            
        except Exception as e:
            print(f"❌ Cycle {cycle_count} error: {e}")
            
        finally:
            # CLEANUP: Delete profile at cycle end
            ProfileManager.cleanup()
            
            # Intersession logic
            await intersession_delay()
```

## Testing Strategy

### Unit Tests: `tests/unit/core/test_profile_manager.py`
```python
class TestProfileManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        ProfileManager.PROFILE_DIR = os.path.join(self.temp_dir, "p")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cleanup_deletes_profile(self):
        """Test cleanup deletes profile folder"""
        # Create test profile
        os.makedirs(ProfileManager.PROFILE_DIR, exist_ok=True)
        assert os.path.exists(ProfileManager.PROFILE_DIR)
        
        # Cleanup
        ProfileManager.cleanup()
        assert not os.path.exists(ProfileManager.PROFILE_DIR)
    
    def test_ensure_fresh_creates_new_profile(self):
        """Test ensure_fresh creates fresh profile folder"""
        # Ensure fresh
        path = ProfileManager.ensure_fresh()
        
        assert os.path.exists(path)
        assert os.path.isdir(path)
    
    def test_ensure_fresh_removes_existing(self):
        """Test ensure_fresh removes existing profile first"""
        # Create existing profile with file
        os.makedirs(ProfileManager.PROFILE_DIR, exist_ok=True)
        with open(os.path.join(ProfileManager.PROFILE_DIR, "test.txt"), "w") as f:
            f.write("test")
        
        # Ensure fresh
        path = ProfileManager.ensure_fresh()
        
        # File should be gone
        assert not os.path.exists(os.path.join(path, "test.txt"))
    
    def test_get_profile_size(self):
        """Test getting profile size"""
        os.makedirs(ProfileManager.PROFILE_DIR, exist_ok=True)
        with open(os.path.join(ProfileManager.PROFILE_DIR, "test.txt"), "w") as f:
            f.write("test content")
        
        size = ProfileManager.get_profile_size()
        assert size > 0
```

## Files to Create/Modify
- [ ] Create: `src/sentinel/profile_manager.py`
- [ ] Create: `tests/unit/core/test_profile_manager.py`
- [ ] Modify: `src/sentinel/run.py` (integrate ProfileManager)

## Success Criteria
- [ ] ProfileManager class created
- [ ] Cleanup runs after every cycle
- [ ] Fresh profile created at cycle start
- [ ] All tests pass
- [ ] No profile accumulation across cycles

## Estimated Time
4-6 hours

## Dependencies
- Phase 0 (Testing Infrastructure)

## Risk Mitigation
- Test cleanup thoroughly to avoid data loss
- Ensure cleanup runs even on error
- Log cleanup actions for debugging
- Make cleanup behavior configurable via env var (optional)
