import json
import re

# 1. THE PALETTE
PALETTE = {
    'SLY': "#ffbf00", 'LY':  "#fec715", 'SY':  "#fecf29", 
    'VY':  "#fdd63e", 'PY':  "#fddc52", 'VLY': "#fde267", 
    'MY':  "#fde87b", 'DPY': "#fded8f", 'DSY': "#fdf1a3",
    'SLB': "#f0f4ff", 'LB':  "#b1c3f9", 'SB':  "#7395cc", 
    'VB':  "#546bfa", 'PB':  "#3a4ebc", 'VLB': "#303d98", 
    'MB':  "#28386a", 'DPB': "#1e155e", 'DSB': "#273b6b",
}

def hex_to_dec(hex_str):
    """Converts hex color string to Discord-compatible decimal."""
    return int(hex_str.lstrip('#'), 16)

palette_dec = {k: hex_to_dec(v) for k, v in PALETTE.items()}

def update_ship_backup(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Fix syntax (handles potential missing commas in the backup file) 
        fixed_content = re.sub(r'}\s*\n\s*{', '},\n{', content)
        data = json.loads(fixed_content)

        # 2. DEFINE THE COLOR SEQUENCE
        color_order = [
            'SLY', 'LY', 'SY', 'VY', 'PY', 'VLY', 'MY', 'DPY', 'DSY',
            'SLB', 'LB', 'SB', 'VB', 'PB', 'VLB', 'MB', 'DPB', 'DSB'
        ]

        # 3. LIST OF CATEGORY HEADERS
        # These names trigger the color change for the entire group
        headers = [
            "🌟 Grand Astronomer", "🛡️ Space Rangers", "🤖 Ship Bots", "🌠 Nebula Beast", 
            "🌜 Moon Guardians", "⭐ Little Astronauts", "💫 Space Flip", "📡 Signal Watcher", 
            "👨🏻‍🚀 He/Him", "🦊 Void Fox", "UTC-11", "🎨 Coloring Squad", "🟢 Full Oxygen", "☄️ Comet Zoomies"
        ]

        roles = data.get('roles', [])
        num_colors = len(color_order)
        
        # We start with the first color
        color_pointer = 0
        current_color_key = color_order[color_pointer]

        # 4. APPLY ONE COLOR PER CATEGORY
        for role in roles:
            role_name = role.get('name', '')
            
            # Check if this role is a new category header
            if any(h in role_name for h in headers):
                # When we hit a header, move to the next color in the palette
                color_pointer = (color_pointer + 1) % num_colors
                current_color_key = color_order[color_pointer]
            
            # Assign the current category color to the role
            role['color'] = palette_dec[current_color_key]

        # 5. SAVE UPDATED FILE
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"Success! Updated {len(roles)} roles grouped by category color.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    update_ship_backup('ship_backup_updated.json', 'ship_backup_updated2.json')