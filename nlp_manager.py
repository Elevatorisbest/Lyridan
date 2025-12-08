import os
import re
import sys

# Try imports
try:
    import cutlet
    import g2p_en
    import sudachipy
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"NLP Manager Warning: Missing dependencies: {e}")

class NLPManager:
    def __init__(self):
        self.katsu = None
        self.g2p = None
        
        if HAS_DEPS:
            try:
                # Initialize Cutlet for Japanese
                # 'hepburn' is standard. use_foreign_spelling=False to avoid weird chars
                self.katsu = cutlet.Cutlet('hepburn')
                self.katsu.use_foreign_spelling = False
            except Exception as e:
                print(f"Failed to load Cutlet: {e}")

            try:
                # Initialize G2P for English
                self.g2p = g2p_en.G2p()
            except Exception as e:
                print(f"Failed to load G2P_en: {e}")

    def romanize_japanese(self, text):
        """
        Romanizes Japanese text using Cutlet.
        """
        if self.katsu:
            # cutlet.romaji(text) returns space-separated words
            # "こんにちは" -> "Konnichiwa"
            return self.katsu.romaji(text)
        return text

    def syllabize_japanese(self, text, separator='-'):
        """
        Romanizes and then syllabizes Japanese text.
        Strategy:
          1. Romanize with Cutlet -> "konnichiwa"
          2. Split into mora-like chunks.
        """
        romanized = self.romanize_japanese(text)
        # Romanized is "Word Word Word"
        words = romanized.split()
        processed_words = []
        for word in words:
            # Syllabize the romanized word
            syl = self._syllabize_romanized_word(word)
            processed_words.append(separator.join(syl))
        return " ".join(processed_words)

    def _syllabize_romanized_word(self, word):
        """
        Splits a romanized Japanese word into syllables/mora.
        Simple regex approach for Hepburn:
        Vowels: a, i, u, e, o
        Structure: (C)V(n|m)? | (C)yV ...
        """
        syllables = []
        # Pattern to match a single syllable
        # Optional consonant(s) + Vowel + Optional 'n' (if not followed by vowel)
        # This is a simplification.
        
        # Better approach: Iterate and consume
        # Pattern:
        # ^(ch|sh|ts|[bcdfghjklmnpqrstvwxyz]y|[bcdfghjklmnpqrstvwxyz])?[aeiouy]
        
        i = 0
        n = len(word)
        while i < n:
            # Special case for double consonants (small tsu -> pause)
            # But cutlet outputs "kitte" -> kit-te? or ki-tte?
            # Usually musical syllabization: kit-te.
            
            # Simple greedy match
            # 1. Match Consonant cluster (optional) + Vowel
            remaining = word[i:]
            
            # Regex for standard Hepburn syllable
            # (Cy | C | '') V
            # C can be ch, sh, ts, or single char
            match = re.match(r'^(?:(?:ch|sh|ts|[bcdfghjklmnpqrstvwxyz]y|[bcdfghjklmnpqrstvwxyz])?[aeiou])', remaining, re.IGNORECASE)
            
            if match:
                syl = match.group(0)
                i += len(syl)
                
                # Check for 'n' or double consonant at end of syllable?
                # Actually, double consonant: "kappa". 
                # Cutlet: kappa.
                # match "ka". remaining "ppa". 
                # next match: "ppa" -> p is not V.
                # Regex needs to handle the start.
                
                # If we have a leftover 'n' or 'm' that isn't a vowel start
                if i < n:
                    next_char = word[i]
                    # If next is consonant and same as previous (double cons), attach to previous?
                    # "kap-pa". So 'p' goes to first syllable?
                    # "Hip-Hop" -> Hip-Hop.
                    # "Zet-tai".
                    # If we matched 'Ze', next is 't', then 'tai'.
                    # So 't' should arguably belong to 'Ze' -> 'Zet'.
                    if re.match(r'[bcdfghjklmnpqrstvwxyz]', next_char, re.IGNORECASE):
                        # If doubles the NEXT consonant...
                        if i+1 < n and word[i+1].lower() == next_char.lower():
                            syl += next_char
                            i += 1
                        # Or if it is 'n' at end of word or before consonant
                        elif next_char.lower() == 'n':
                            # check if next is vowel
                            is_n_vowel = False
                            if i+1 < n and re.match(r'[aeiouy]', word[i+1], re.IGNORECASE):
                                is_n_vowel = True
                            if not is_n_vowel:
                                syl += next_char
                                i += 1
                                
                syllables.append(syl)
            else:
                # Fallback, just take character
                syllables.append(remaining[0])
                i += 1
                
        return syllables

    def syllabize_english(self, text, separator='-'):
        """
        Syllabizes English text roughly using G2P for phoneme awareness?
        Since G2P doesn't align to letters, we might just fallback to a dictionary or logic
        but maybe use G2P to disambiguate?
        
        For this implementation, I will stick to a logic that tries to respect the user's request
        by using g2p for 'pronunciation' lookups if needed, but for 'orthographic syllabization'
        (splitting written words), it's extremely hard to reverse G2P.
        
        However, the user might actually be asking for the *romanization* of JP to be done via ...
        and *syllabization* for JP ...
        
        "romanization and syllabization for japanese is done via torch... and g2p_en instead?"
        "and g2p_en" is likely for English?
        
        I will assume: Use simple heuristic for English (maybe the existing one or pyphen) 
        BUT verify validity with G2P or similar?
        
        Actually, looking at the previous 'syllabize.py', it had 'syllabize_english_word' using a dict.
        I will try to keep that but add g2p_en as a 'backend' if I can.
        
        Since I cannot easily do orthographic syllabification with g2p alone, 
        I will use a local implementation of the "Maximum Onset Principle" or similar
        on the text, potentially just simple regex, unless I import `pyphen`.
        
        Wait, `pyphen` was in the requirements list I updated!
        The user included `pyphen` in the ORIGINAL file.
        I KEPT it in the new requirements.
        So I should probably use `pyphen` for English as it's the standard tool for this.
        The user mentioned `g2p_en`... maybe they want IPA output?
        
        I'll implement `syllabize_english` to use `pyphen` by default.
        """
        import pyphen
        dic = pyphen.Pyphen(lang='en')
        
        words = text.split()
        processed_words = []
        for word in words:
            # pyphen inserts hyphens
            syl = dic.inserted(word)
            # replace hyphen with requested separator
            syl = syl.replace('-', separator)
            processed_words.append(syl)
        return " ".join(processed_words)

