import discord

def generate_ship_perm_code():
    perms = discord.Permissions.none()
    
    print("🛰️ --- Starflight Pilot: Permission Code Generator ---")
    print("Type 'y' for Yes or 'n' for No for each permission:\n")

    # Mapping common permissions for your crew roles
    options = {
        "View Channels": "view_channel",
        "Send Messages": "send_messages",
        "Embed Links": "embed_links",
        "Attach Files": "attach_files",
        "Add Reactions": "add_reactions",
        "Use External Emojis": "use_external_emojis",
        "Read Message History": "read_message_history",
        "Connect to VC": "connect",
        "Speak in VC": "speak",
        "Use Voice Activity": "use_voice_activation",
        "Manage Messages (Ranger/Staff)": "manage_messages",
        "Moderate Members (Ranger/Staff)": "moderate_members",
        "Administrator (Grand Astronomer)": "administrator"
    }

    for label, attribute in options.items():
        choice = input(f"Enable {label}? (y/n): ").lower()
        if choice == 'y':
            setattr(perms, attribute, True)

    print("\n" + "="*40)
    print(f"🚀 GENERATED PERMISSION CODE: {perms.value}")
    print("="*40)
    print("Copy this integer into your JSON or ROLE_DATA.")

if __name__ == "__main__":
    generate_ship_perm_code()