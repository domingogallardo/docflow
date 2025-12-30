#!/usr/bin/env python3
"""
Update HTML typography to the standard system font.

Usage:
    python update_font.py <directory>
    python update_font.py /path/to/html/files

Example:
    python update_font.py "/Users/domingo/⭐️ Documentación/Posts/Posts 2025"
"""
import sys
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
import re

# System font we want to use.
SYSTEM_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

def update_font_in_html(html_file: Path) -> bool:
    """
    Update typography in an HTML file.
    
    Returns:
        bool: True if changes were made, False otherwise.
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        changed = False
        
        # Find <style> tags.
        style_tags = soup.find_all('style')
        
        if style_tags:
            # Update font-family in existing <style> tags.
            for style_tag in style_tags:
                if style_tag.string:
                    css_content = style_tag.string
                    
                    # Find and replace existing font-family.
                    font_pattern = r'font-family\s*:\s*[^;]+;?'
                    if re.search(font_pattern, css_content):
                        new_css = re.sub(font_pattern, f'font-family: {SYSTEM_FONT};', css_content)
                        style_tag.string = new_css
                        changed = True
                    else:
                        # If there is no font-family, add it to body if present.
                        if 'body' in css_content:
                            # Find the body rule and add font-family.
                            body_pattern = r'(body\s*\{[^}]*)'
                            if re.search(body_pattern, css_content):
                                def add_font_to_body(match):
                                    body_rule = match.group(1)
                                    if body_rule.endswith('{'):
                                        return f"{body_rule} font-family: {SYSTEM_FONT};"
                                    else:
                                        return f"{body_rule} font-family: {SYSTEM_FONT};"
                                
                                new_css = re.sub(body_pattern, add_font_to_body, css_content)
                                style_tag.string = new_css
                                changed = True
        else:
            # No <style> tags; create a new one.
            head = soup.head
            if head is None:
                # If there is no <head>, create it.
                head = soup.new_tag("head")
                if soup.html:
                    soup.html.insert(0, head)
                else:
                    # If there is no <html>, insert <head> at the start.
                    soup.insert(0, head)
            
            # Create a new <style> tag with the font.
            style_tag = soup.new_tag("style")
            style_tag.string = f"body {{ font-family: {SYSTEM_FONT}; }}"
            head.append(style_tag)
            changed = True
        
        # Save changes if any were made.
        if changed:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error processing {html_file}: {e}")
        return False

def find_html_files(directory: Path) -> list[Path]:
    """Find all HTML files in a directory."""
    html_files = []
    
    if directory.is_file() and directory.suffix.lower() in ['.html', '.htm']:
        # Single HTML file.
        html_files.append(directory)
    elif directory.is_dir():
        # If it is a directory, search for HTML files.
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in ['.html', '.htm']:
                html_files.append(file_path)
    
    return html_files

def main():
    parser = argparse.ArgumentParser(
        description="Update HTML typography to the system font"
    )
    parser.add_argument(
        'directory',
        help='Directory or HTML file to process'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show which files would be processed without making changes'
    )
    
    args = parser.parse_args()
    
    target_path = Path(args.directory)
    
    if not target_path.exists():
        print(f"❌ Error: The directory/file '{target_path}' does not exist")
        sys.exit(1)
    
    # Find HTML files.
    html_files = find_html_files(target_path)
    
    if not html_files:
        print(f"📄 No HTML files found in '{target_path}'")
        return
    
    print(f"🔍 Found {len(html_files)} HTML file(s)")
    print(f"🎨 Target font: {SYSTEM_FONT}")
    
    if args.dry_run:
        print("\n📋 Files that would be processed:")
        for html_file in html_files:
            print(f"  • {html_file}")
        print("\n💡 Run without --dry-run to apply changes")
        return
    
    # Process files.
    updated_count = 0
    
    for html_file in html_files:
        try:
            if update_font_in_html(html_file):
                print(f"✅ Updated: {html_file.name}")
                updated_count += 1
            else:
                print(f"⏭️  No changes: {html_file.name}")
        
        except Exception as e:
            print(f"❌ Error: {html_file.name} - {e}")
    
    print("\n🎉 Processing complete:")
    print(f"   • {updated_count} files updated")
    print(f"   • {len(html_files) - updated_count} files unchanged")

if __name__ == "__main__":
    main() 
