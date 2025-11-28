import re
import json
import xml.etree.ElementTree as ET
import os

# Try to import pykakasi for Japanese romanization
kks = None
try:
    from pykakasi import kakasi
    kks = kakasi()
    kks.setMode('H', 'a')
    kks.setMode('K', 'a')
    kks.setMode('J', 'a')
except ImportError:
    pass

# Load English syllabification dictionary
english_dict = {}
try:
    dict_path = os.path.join(os.path.dirname(__file__), 'English.txt')
    if os.path.exists(dict_path):
        with open(dict_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '•' in line:
                    # Store as lowercase key -> syllabified value
                    english_dict[line.replace('•', '').lower()] = line
except Exception as e:
    print(f"Warning: Could not load English.txt: {e}")

# Try to import transliterate for Russian
HAS_TRANSLITERATE = False
try:
    from transliterate import translit
    HAS_TRANSLITERATE = True
except ImportError:
    pass

def detect_language(text):
    """
    Simple heuristic to detect language based on character sets.
    Returns: 'japanese', 'russian', 'mixed', or 'other'
    """
    has_japanese = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text))
    has_russian = bool(re.search(r'[а-яА-Я]', text))
    
    if has_japanese and has_russian:
        return 'mixed'
    elif has_japanese:
        return 'japanese'
    elif has_russian:
        return 'russian'
    return 'other'

def ttml_time_to_seconds(ttml_time):
    """
    Converts TTML time string to seconds (float).
    TTML: "20.501" (seconds) or "1:00.233" (mm:ss.ms)
    """
    try:
        if ':' in ttml_time:
            parts = ttml_time.split(':')
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            elif len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            else:
                return 0.0
        else:
            return float(ttml_time)
    except:
        return 0.0

def convert_ttml_time(ttml_time):
    """
    Converts TTML time string to LRC timestamp format.
    """
    total_seconds = ttml_time_to_seconds(ttml_time)
    m_int = int(total_seconds // 60)
    s_float = total_seconds % 60
    s_int = int(s_float)
    cs = int((s_float - s_int) * 100)
    return f"{m_int:02d}:{s_int:02d}.{cs:02d}"

def extract_ttml_data(file_path):
    """
    Parses TTML and returns a list of data dictionaries:
    [{'start': float, 'end': float, 'text': str, 'line_id': str}, ...]
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check for JSON wrapper
        if content.strip().startswith('{'):
            data = json.loads(content)
            try:
                ttml_content = data['data'][0]['attributes']['ttmlLocalizations']
            except (KeyError, IndexError, TypeError):
                match = re.search(r'<tt.*?</tt>', content, re.DOTALL)
                if match:
                    ttml_content = match.group(0)
                else:
                    raise ValueError("Could not find TTML content in JSON")
        else:
            ttml_content = content

        # Parse XML
        ttml_content = re.sub(r'^<\?xml.*?\?>', '', ttml_content).strip()
        root = ET.fromstring(ttml_content)
        
        ns = {
            'tt': 'http://www.w3.org/ns/ttml',
            'itunes': 'http://music.apple.com/lyric-ttml-internal'
        }
        
        # Find transliterations
        trans_root = None
        for trans in root.iter():
            if trans.tag.endswith('transliteration'):
                # Prefer ja-Latn or just take the first one
                trans_root = trans
                break
        
        source_root = trans_root if trans_root is not None else None
        
        extracted_spans = []
        
        if source_root is not None:
            # Extract from transliteration
            for text_node in source_root.iter():
                if text_node.tag.endswith('text'):
                    line_id = text_node.attrib.get('for')
                    for span in text_node.iter():
                        if span.tag.endswith('span') and span.text:
                            begin = span.attrib.get('begin')
                            end = span.attrib.get('end')
                            if begin and end:
                                extracted_spans.append({
                                    'start': ttml_time_to_seconds(begin),
                                    'end': ttml_time_to_seconds(end),
                                    'text': span.text,
                                    'line_id': line_id
                                })
        else:
            # Extract from body
            for p in root.iter():
                if p.tag.endswith('p'):
                    line_id = p.attrib.get(f'{{{ns["itunes"]}}}key')
                    for span in p.iter():
                        if span.tag.endswith('span') and span.text:
                            begin = span.attrib.get('begin')
                            end = span.attrib.get('end')
                            if begin and end:
                                extracted_spans.append({
                                    'start': ttml_time_to_seconds(begin),
                                    'end': ttml_time_to_seconds(end),
                                    'text': span.text,
                                    'line_id': line_id
                                })
                                
        return extracted_spans

    except Exception as e:
        print(f"Error extracting TTML data: {e}")
        return []

def parse_ttml(file_path):
    """
    Parses a TTML file and returns a list of strings in LRC format.
    Uses extract_ttml_data to get the raw data first.
    """
    data = extract_ttml_data(file_path)
    lrc_lines = []
    
    # Group by line_id to reconstruct lines for LRC
    current_line_id = None
    current_line_parts = []
    current_start_time = 0.0
    
    for item in data:
        if item['line_id'] != current_line_id:
            if current_line_id is not None:
                # Flush previous line
                # Use the start time of the first span
                lrc_timestamp = convert_ttml_time(str(current_start_time))
                full_text = "".join(current_line_parts).strip()
                lrc_lines.append(f"[{lrc_timestamp}] {full_text}")
            
            current_line_id = item['line_id']
            current_line_parts = []
            current_start_time = item['start']
            
        current_line_parts.append(item['text'])
        
    # Flush last line
    if current_line_id is not None:
        lrc_timestamp = convert_ttml_time(str(current_start_time))
        full_text = "".join(current_line_parts).strip()
        lrc_lines.append(f"[{lrc_timestamp}] {full_text}")
        
    return lrc_lines

def parse_rocksmith_beatmap(xml_path):
    """Parses a Rocksmith XML file to extract beat times."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ebeats = root.find('ebeats')
        if ebeats is None:
            return []
        
        beats = []
        for ebeat in ebeats.findall('ebeat'):
            time_val = float(ebeat.get('time'))
            beats.append(time_val)
        return sorted(beats)
    except Exception as e:
        print(f"Error parsing beatmap: {e}")
        return []

def snap_to_grid(time_val, beats, resolution=16):
    """
    Snaps a time value to the nearest grid point based on beats.
    resolution: 4 (quarter), 8 (eighth), 16 (sixteenth), etc.
    """
    if not beats:
        return time_val
        
    import bisect
    idx = bisect.bisect_right(beats, time_val)
    
    if idx == 0:
        return beats[0]
    if idx >= len(beats):
        return beats[-1]
        
    t1 = beats[idx-1]
    t2 = beats[idx]
    
    duration = t2 - t1
    
    subdivisions = resolution // 4
    if subdivisions < 1: subdivisions = 1
    
    grid_points = []
    step = duration / subdivisions
    for i in range(subdivisions + 1):
        grid_points.append(t1 + i * step)
        
    closest_time = min(grid_points, key=lambda x: abs(x - time_val))
    return closest_time

def export_rocksmith_xml(data, output_path, offset=10.0, beatmap_path=None, empty_measure=False):
    """
    Exports syllabized lyrics to Rocksmith XML format.
    
    Args:
        data: List of (timestamp, text) tuples.
        output_path: Path to save the XML file.
        offset: Time offset in seconds to add to all timestamps.
        beatmap_path: Path to Rocksmith XML beatmap for snapping.
        empty_measure: If True, adds the duration of the first measure to the offset.
    """
    import xml.etree.ElementTree as ET
    
    root = ET.Element("vocals", count=str(len(data)))
    
    beats = []
    measure_duration = 0.0
    
    if beatmap_path:
        beats = parse_rocksmith_beatmap(beatmap_path)
        if empty_measure and len(beats) >= 2:
            # Estimate measure duration from first beat interval * 4 (assuming 4/4)
            beat_interval = beats[1] - beats[0]
            measure_duration = beat_interval * 4.0
    
    final_offset = offset + measure_duration

    for i, item in enumerate(data):
        text = item['text']
        time_val = item['start']
        
        # Apply Offset
        time_val += final_offset
        
        # Snap to grid if beatmap is provided
        if beats:
            time_val = snap_to_grid(time_val, beats)
        
        words = text.split()
        current_time = time_val
        
        for w_idx, word in enumerate(words):
            lang = detect_language(word)
            syllables = []
            if lang == 'japanese':
                syl_str = syllabize_word(word, separator='-')
                syllables = syl_str.split('-')
            elif lang == 'russian':
                syl_str = syllabize_russian_word(word, separator='-')
                syllables = syl_str.split('-')
            else:
                syl_str = syllabize_english_word(word, separator='-')
                syllables = syl_str.split('-')
            
            for s_idx, syl in enumerate(syllables):
                vocal = ET.SubElement(root, "vocal")
                vocal.set("time", f"{current_time:.3f}")
                vocal.set("note", "0")
                vocal.set("length", "0.200")
                
                is_last_syllable = (s_idx == len(syllables) - 1)
                is_last_word = (w_idx == len(words) - 1)
                
                lyric_text = syl
                if not is_last_syllable:
                    lyric_text += "-"
                elif not is_last_word:
                    lyric_text += "+"
                else:
                    # Last syllable of last word
                    # Check if this is the end of the line (phrase)
                    is_end_of_phrase = False
                    if i == len(data) - 1:
                        is_end_of_phrase = True
                    elif data[i+1]['line_id'] != item['line_id']:
                        is_end_of_phrase = True
                    
                    if is_end_of_phrase:
                        lyric_text += "+"
                
                vocal.set("lyric", lyric_text)
                current_time += 0.25 

    tree = ET.ElementTree(root)
    try:
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error writing XML: {e}")
        return False

def syllabize_russian_word(word, separator="+"):
    vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
    syllables = []
    n = len(word)
    vowel_indices = [j for j, char in enumerate(word) if char in vowels]
    
    if not vowel_indices:
        return word 
        
    start = 0
    for k, v_idx in enumerate(vowel_indices):
        if k == len(vowel_indices) - 1:
            end = n
        else:
            next_v_idx = vowel_indices[k+1]
            num_consonants = next_v_idx - v_idx - 1
            
            if num_consonants == 0:
                end = v_idx + 1
            elif num_consonants == 1:
                end = v_idx + 1
            else:
                consonant_start = v_idx + 1

                first_consonant = word[consonant_start]
                if first_consonant.lower() == 'й':
                    end = consonant_start + 1 
                else:
                    end = next_v_idx - 1
        
        syllables.append(word[start:end])
        start = end
        
    return separator.join(syllables)

def syllabize_english_word(word, separator="+"):
    # Strip punctuation
    match = re.match(r'^([^\w]*)(.*?)([^\w]*)$', word)
    if not match:
        return word
        
    prefix, core, suffix = match.groups()
    
    if not core:
        return word
        
    lower_core = core.lower()
    
    # Look up in English.txt dictionary
    if lower_core in english_dict:
        syllabified = english_dict[lower_core]
        # Replace • with the desired separator
        syllabified = syllabified.replace('•', separator)
        
        # Preserve capitalization
        if core[0].isupper():
            # Simple capitalization - capitalize first letter
            syllabified = syllabified[0].upper() + syllabified[1:] if len(syllabified) > 0 else syllabified
        if core.isupper() and len(core) > 1:
            # All caps - capitalize all
            syllabified = syllabified.upper()
            
        return f"{prefix}{syllabified}{suffix}"
    
    # If not found in dictionary, return as-is
    return word

def syllabize_word(word, separator="+", language="japanese"):
    if language == 'russian':
        return syllabize_russian_word(word, separator)
    elif language == 'english' or language == 'other':
        return syllabize_english_word(word, separator)
        
    syllables = []
    i = 0
    n = len(word)
    
    while i < n:
        remaining = word[i:]
        
        core_pattern = r'^(?:(?:ch|sh|ts|[bcdfghjklmnpqrstvwxyz]y)[aeiou]|(?:ch|sh|ts|[bcdfghjklmnpqrstvwxyz])[aeiouy]|[aeiouy])'
        match = re.match(core_pattern, remaining, re.IGNORECASE)
        
        if not match:
            syllables.append(remaining[0])
            i += 1
            continue
            
        current_syllable = match.group(0)
        i += len(current_syllable)
        
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
    match = re.match(r'^(\[.*?\])(.*)', line)
    if not match:
        return line 
    
    timestamp = match.group(1)
    text = match.group(2)
    
    lang = language_override if language_override else detect_language(text)
    
    if lang == 'japanese' and romanize and kks:
        result = kks.convert(text)
        romanized_text = ""
        for item in result:
            romanized_text += item['hepburn'] + " " 
        text = romanized_text.strip()
        text = re.sub(r'\s+', ' ', text)
        
    elif lang == 'russian' and romanize and HAS_TRANSLITERATE:
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
            
        if lang == 'russian':
            syll = syllabize_russian_word(word, separator)
            if romanize and HAS_TRANSLITERATE:
                syll = translit(syll, 'ru', reversed=True)
            syllabized_words.append(syll)
        else:
            # Use detected language, defaulting to japanese logic if it was detected as japanese, 
            # otherwise use the detected lang (which might be 'other' -> english)
            syllabized_words.append(syllabize_word(word, separator, language=lang))
        
    return f"{timestamp} {' '.join(syllabized_words)}"

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
