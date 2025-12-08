
import sys
import os

# Ensure we can import from the directory
sys.path.append(os.getcwd())

def test_nlp_manager():
    print("Testing NLPManager...")
    try:
        from nlp_manager import NLPManager
        nlp = NLPManager()
    except Exception as e:
        print(f"FAILED to import/init NLPManager: {e}")
        return

    # Test Japanese Romanization (Cutlet)
    jp_text = "こんにちは"
    rom = nlp.romanize_japanese(jp_text)
    print(f"JP Romanization: '{jp_text}' -> '{rom}'")
    
    # Test Japanese Syllabization
    syl_jp = nlp.syllabize_japanese(jp_text)
    print(f"JP Syllabization: '{jp_text}' -> '{syl_jp}'")

    # Test English Syllabization (Longer word)
    en_text = "university extraordinary"
    syl_en = nlp.syllabize_english(en_text)
    print(f"EN Syllabization: '{en_text}' -> '{syl_en}'")
    
    if "-" in syl_en:
        print("  [PASS] EN Syllabization has hyphens.")
    else:
        print("  [FAIL] EN Syllabization has NO hyphens.")
        
    # Check if dependencies are actually loaded
    print(f"Cutlet loaded: {nlp.katsu is not None}")
    print(f"G2P loaded: {nlp.g2p is not None}")

    print("\nNLPManager tests completed.")

if __name__ == "__main__":
    test_nlp_manager()
