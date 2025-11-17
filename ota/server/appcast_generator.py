import os
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from utils.logger_helper import logger_helper as logger

class AppcastGenerator:
    def __init__(self, server_root, signatures_dir, template_name='appcast_template.xml'):
        self.server_root = server_root
        self.signatures_dir = signatures_dir
        self.env = Environment(loader=FileSystemLoader(server_root))
        self.template = self.env.get_template(template_name)

    def _find_latest_signatures(self):
        try:
            files = [f for f in os.listdir(self.signatures_dir) if f.startswith('signatures_') and f.endswith('.json')]
            if not files:
                logger.warning("[APPCAST] ❌ No signature files found.")
                return None, None
            
            latest_file = sorted(files, reverse=True)[0]
            version = latest_file.replace('signatures_', '').replace('.json', '')
            logger.info(f"[APPCAST] 🔍 Using latest signature file: {latest_file}")
            return os.path.join(self.signatures_dir, latest_file), version
        except Exception as e:
            logger.error(f"[APPCAST] Error finding signature files: {e}")
            return None, None

    def generate(self, base_url):
        signatures_path, version = self._find_latest_signatures()
        if not signatures_path:
            return None

        with open(signatures_path, 'r') as f:
            signatures_data = json.load(f)

        items = []
        for filename, data in signatures_data.items():
            os_type = "macos" if "darwin" in filename else "windows" if "windows" in filename else "linux"
            
            item = {
                'title': f'Version {version}',
                'description': f'<h2>What\'s New in eCan {version}</h2><ul><li>Bug fixes and performance improvements.</li></ul>',
                'pub_date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                'download_url': f'{base_url}/downloads/{filename}',
                'version': version,
                'os': os_type,
                'file_size': data.get('file_size', 0),
                'signature': data.get('signature', '')
            }
            items.append(item)
        
        if not items:
            logger.warning("[APPCAST] 텅 No items to add to appcast.")
            return None

        xml_content = self.template.render(
            base_url=base_url,
            build_date=datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
            items=items
        )
        
        output_path = os.path.join(self.server_root, 'appcast.xml')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        logger.info(f"[APPCAST] ✅ Generated: {output_path}")
        logger.info(f"[APPCAST] 📦 Contains {len(items)} update items.")
        return xml_content

    def generate_from_latest_signatures(self, base_url):
        """Generate appcast from latest signature file"""
        return self.generate(base_url) is not None

    def generate_appcast(self, version, base_url, output_filename='appcast.xml'):
        """Generate appcast for specified version"""
        try:
            signatures_path = os.path.join(self.signatures_dir, f'signatures_{version}.json')
            if not os.path.exists(signatures_path):
                logger.warning(f"[APPCAST] ❌ Signature file not found for version {version}")
                return False

            with open(signatures_path, 'r') as f:
                signatures_data = json.load(f)

            items = []
            for filename, data in signatures_data.items():
                os_type = "macos" if "darwin" in filename else "windows" if "windows" in filename else "linux"
                
                item = {
                    'title': f'Version {version}',
                    'description': f'<h2>What\'s New in eCan {version}</h2><ul><li>Bug fixes and performance improvements.</li></ul>',
                    'pub_date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                    'download_url': f'{base_url}/downloads/{filename}',
                    'version': version,
                    'os': os_type,
                    'file_size': data.get('file_size', 0),
                    'signature': data.get('signature', '')
                }
                items.append(item)
            
            if not items:
                logger.warning(f"[APPCAST] ❌ No items to add to appcast for version {version}")
                return False

            xml_content = self.template.render(
                base_url=base_url,
                build_date=datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                items=items
            )
            
            output_path = os.path.join(self.server_root, output_filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            logger.info(f"[APPCAST] ✅ Generated: {output_path}")
            logger.info(f"[APPCAST] 📦 Contains {len(items)} update items for version {version}")
            return True
        except Exception as e:
            logger.error(f"[APPCAST] Error generating appcast for version {version}: {e}")
            return False

