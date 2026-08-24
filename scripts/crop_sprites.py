import os
from pathlib import Path
from PIL import Image

def crop_sprite_sheets():
    root = Path(__file__).parent.parent
    assets_dir = root / "assets" / "characters"
    
    jack_path = assets_dir / "Jack.png"
    jill_path = assets_dir / "Jill.png"
    
    if not jack_path.exists() or not jill_path.exists():
        print("Missing Jack.png or Jill.png in assets/characters/")
        return
        
    jack_out_dir = assets_dir / "jack"
    jill_out_dir = assets_dir / "jill"
    jack_out_dir.mkdir(exist_ok=True)
    jill_out_dir.mkdir(exist_ok=True)
    
    # Jill expressions list
    jill_expressions = [
        "playful_wink_joy",
        "gentle_smile_content",
        "infatuated_in_love",
        "annoyed_pouting",
        "pensive_curious",
        "crying_distressed",
        "shocked_surprised",
        "friendly_wave_greeting",
        "sparkling_proud"
    ]
    
    # Jack expressions list
    jack_expressions = [
        "sad_pouting",
        "furious_shouting",
        "stern_cross_armed_grumpy",
        "joyful_laugh_closed_eyes",
        "gasp_astonished",
        "smug_scheming",
        "winking_mischief_laugh",
        "shy_love_flattered",
        "hyped_celebrating"
    ]
    
    # Crop Jill
    with Image.open(jill_path) as im:
        w, h = im.size
        cw, ch = w // 3, h // 3
        for idx, exp in enumerate(jill_expressions):
            row = idx // 3
            col = idx % 3
            box = (col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)
            cropped = im.crop(box)
            cropped.save(jill_out_dir / f"{exp}.png", "PNG")
            print(f"Saved Jill: {exp}.png")
            
    # Crop Jack
    with Image.open(jack_path) as im:
        w, h = im.size
        cw, ch = w // 3, h // 3
        for idx, exp in enumerate(jack_expressions):
            row = idx // 3
            col = idx % 3
            box = (col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)
            cropped = im.crop(box)
            cropped.save(jack_out_dir / f"{exp}.png", "PNG")
            print(f"Saved Jack: {exp}.png")

if __name__ == "__main__":
    crop_sprite_sheets()
