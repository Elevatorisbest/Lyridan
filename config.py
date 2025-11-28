import json
import os
from pathlib import Path

class Config:
    def __init__(self):
        # Store config in user's AppData/Roaming directory for Windows
        if os.name == 'nt':
            self.config_dir = Path(os.getenv('APPDATA')) / 'Lyridan'
        else:
            self.config_dir = Path.home() / '.lyridan'
        
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / 'options.lrdn'
        
        self.defaults = {
            'warnings': {
                'rocksmith_export': True,
                'lrc_save': True
            },
            'theme': 'Dark'
        }
        
        self.settings = self.load()
    
    def load(self):
        """Load config from file, or create with defaults if not exists"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.defaults.copy()
        else:
            # Create default config
            self.save(self.defaults)
            return self.defaults.copy()
    
    def save(self, settings=None):
        """Save config to file"""
        if settings is None:
            settings = self.settings
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key, default=None):
        """Get a setting value"""
        keys = key.split('.')
        value = self.settings
        for k in keys:
            value = value.get(k, default)
            if value is None:
                return default
        return value
    
    def set(self, key, value):
        """Set a setting value and save"""
        keys = key.split('.')
        current = self.settings
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.save()
    
    def reset_warnings(self):
        """Reset all warning acknowledgments"""
        self.settings['warnings'] = self.defaults['warnings'].copy()
        self.save()
