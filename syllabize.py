import re
import sys
try:
    import pykakasi
    kks = pykakasi.kakasi()
except ImportError:
    kks = None

try:
    from transliterate import translit
    HAS_TRANSLITERATE = True
except ImportError:
    HAS_TRANSLITERATE = False

def detect_language(text):
    # Simple heuristic detection
    # Check for Cyrillic
    if re.search(r'[а-яА-ЯёЁ]', text):
        # Check if also has Japanese
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text):
            return 'mixed'
        return 'russian'
    # Check for Japanese
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text):
        return 'japanese'
    return 'other'

def syllabize_russian_word(word, separator="+"):
    # Russian syllabization rules are complex, but we can approximate based on sonority.
    # Vowels: а, е, ё, и, о, у, ы, э, ю, я
    vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
    
    syllables = []
    current_syllable = ""
    
    # Simple algorithm:
    # 1. Split by vowels. Each syllable must have exactly one vowel.
    # 2. Consonants usually go to the next syllable (Onset), unless it violates sonority or is 'й'.
    
    # Let's use a simpler regex approach similar to the Japanese one but adapted.
    # We iterate and build syllables.
    
    # Tokenize into (Consonants*)(Vowel)(Consonants*)
    # But Russian allows complex clusters.
    
    # Alternative:
    # Iterate through chars.
    # If char is vowel, it ends the onset of current syllable (or starts it if no onset).
    # Actually, standard rule: V-CV.
    
    # Let's try a pass-through approach.
    
    n = len(word)
    i = 0
    
    # We need to identify vowel positions
    vowel_indices = [j for j, char in enumerate(word) if char in vowels]
    
    if not vowel_indices:
        return word # No vowels, one syllable (or abbreviation)
        
    start = 0
    for k, v_idx in enumerate(vowel_indices):
        # Determine end of this syllable
        # If it's the last vowel, end is end of word
        if k == len(vowel_indices) - 1:
            end = n
        else:
            # Look at consonants between this vowel and next vowel
            next_v_idx = vowel_indices[k+1]
            num_consonants = next_v_idx - v_idx - 1
            
            # Rule of thumb:
            # 0 consonants: V-V (e.g. a-u) -> split after V
            # 1 consonant: V-CV -> split before C
            # 2+ consonants: V-CCV or VC-CV?
            # Usually split before the last consonant of the cluster (to maximize onset of next syllable)
            # Unless the first consonant is 'й' (short i), then it stays as coda: Vi-CV
            
            if num_consonants == 0:
                end = v_idx + 1
            elif num_consonants == 1:
                end = v_idx + 1
            else:
                # Check for 'й'
                consonant_start = v_idx + 1
                first_consonant = word[consonant_start]
                if first_consonant.lower() == 'й':
                    end = consonant_start + 1 # Split after й
                else:
                    # Split before the last consonant
                    end = next_v_idx - 1
        
        syllables.append(word[start:end])
        start = end
        
    return separator.join(syllables)

def syllabize_word(word, separator="+", language="japanese"):
    if language == 'russian':
        return syllabize_russian_word(word, separator)
        
    # Default Japanese/Romaji logic
    syllables = []
    i = 0
    n = len(word)
    
    while i < n:
        remaining = word[i:]
        
        # 1. Match Core Syllable (Onset + Nucleus)
        core_pattern = r'^(?:(?:ch|sh|ts|[bcdfghjklmnpqrstvwxyz]y)[aeiou]|(?:ch|sh|ts|[bcdfghjklmnpqrstvwxyz])[aeiouy]|[aeiouy])'
        match = re.match(core_pattern, remaining, re.IGNORECASE)
        
        if not match:
            syllables.append(remaining[0])
            i += 1
            continue
            
        current_syllable = match.group(0)
        i += len(current_syllable)
        
        # 2. Check for Coda (Moraic 'n' or Sokuon)
        if i < n:
            next_char = word[i]
            if next_char.lower() == 'n':
                is_onset = False
                if i + 1 < n:
                    after_n = word[i+1]
                    if re.match(r'[aeiouy]', after_n, re.IGNORECASE):
                        is_onset = True
                if not is_onset:
                    current_syllable += next_char
                    i += 1
            elif re.match(r'[bcdfghjklmpqrstvwxyz]', next_char, re.IGNORECASE):
                if i + 1 < n:
                    after_c = word[i+1]
                    if next_char.lower() == after_c.lower() or (next_char.lower() == 't' and after_c.lower() == 'c'):
                        current_syllable += next_char
                        i += 1
        
        syllables.append(current_syllable)
        
    return separator.join(syllables)

def process_line(line, separator="+", romanize=False, capitalize=False, language_override=None):
    # Extract timestamp and text
    match = re.match(r'^(\[.*?\])(.*)', line)
    if not match:
        return line 
    
    timestamp = match.group(1)
    text = match.group(2)
    
    # Detect language if not provided or if mixed
    lang = language_override if language_override else detect_language(text)
    
    if lang == 'japanese' and romanize and kks:
        result = kks.convert(text)
        romanized_text = ""
        for item in result:
            romanized_text += item['hepburn'] + " " 
        text = romanized_text.strip()
        text = re.sub(r'\s+', ' ', text)
        
    elif lang == 'russian' and romanize and HAS_TRANSLITERATE:
        # Transliterate Russian
        try:
            text = translit(text, 'ru', reversed=True)
            # After transliteration, we should treat it as "japanese-like" (CV structure) or just use the Russian logic?
            # The request says "support for all the same features... for Russian".
            # If we transliterate, we get Latin chars. We should probably syllabize the Cyrillic FIRST, then transliterate?
            # Or transliterate then syllabize?
            # Usually for karaoke, you want the syllables of the romanized text.
            # But Russian phonology is different.
            # Let's stick to: Syllabize the original Russian, THEN transliterate the parts?
            # Or Transliterate then Syllabize?
            # Transliterated Russian doesn't strictly follow CV.
            # Let's assume we syllabize the Russian text using Russian rules, then transliterate the result if requested.
            pass # We will handle this in the word loop
        except Exception:
            pass

    if capitalize:
        text = text.strip()
        if text:
            text = text[0].upper() + text[1:]
    
    words = text.split(' ')
    syllabized_words = []
    
    for word in words:
        if not word:
            syllabized_words.append("")
            continue
            
        # If Russian and we want to transliterate, we have two options:
        # 1. Syllabize Cyrillic -> Transliterate Syllables
        # 2. Transliterate -> Syllabize Latin (might be messy)
        # Let's go with 1.
        
        if lang == 'russian':
            syll = syllabize_russian_word(word, separator)
            if romanize and HAS_TRANSLITERATE:
                # Transliterate the whole syllabized string
                # transliterate handles non-cyrillic chars gracefully usually
                syll = translit(syll, 'ru', reversed=True)
            syllabized_words.append(syll)
        else:
            # Japanese/Romaji
            syllabized_words.append(syllabize_word(word, separator, language='japanese'))
        
    return f"{' '.join(syllabized_words)}"

def main():
    input_file = 'test.lrc'
    output_file = 'output.txt'
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        processed_lines = [process_line(line.strip()) for line in lines]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(processed_lines))
            
        print(f"Successfully processed {input_file} to {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
