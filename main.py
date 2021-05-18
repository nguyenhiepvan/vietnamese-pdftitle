#!/usr/bin/env python

"""
Extracts title from PDF files (Python 3).
Depends on: pdf, pyPDF2, PDFMiner3k, unidecode.
Usage:
    pdftitle -d tmp --rename *.pdf{}
"""

from io import StringIO
import getopt, os, re, string, sys, glob, unidecode
import os 

from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError
from ftfy import fix_encoding
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTChar, LTText, LTFigure, LTTextBox, LTTextLine
from operator import itemgetter
import json


def make_parsing_state(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('ParsingState', (), enums)

def log(text):
    if IS_LOG_ON:
        print ('-------- ' + text)

dir_path = os.path.dirname(os.path.realpath(__file__))
CHAR_PARSING_STATE = make_parsing_state('INIT_X', 'INIT_D', 'INSIDE_WORD')
IS_LOG_ON = False
ONE_CLICK_MODE = True
MIN_CHARS = 6
MAX_WORDS = 20
MIN_LONGEST_WORD = 4

f = open(dir_path + '/unexpected_keywords.json')
UNEXPECTED_KEYWORDS = json.load(f)
def max_word_length(text):
    return max(len(w) for w in text.split(' '))

def sanitize(filename):
    """Turn string into a valid file name.
    """
    # If the title was picked up from text, it may be too large.
    # Preserve a certain number of words
    words = filename.split(' ')
    filename = ' '.join(words[0:MAX_WORDS])

    # Preserve letters with diacritics
    try:
        filename = filename.encode('utf-8').decode('utf-8')
    except UnicodeDecodeError:
        print("*** Skipping invalid title decoding***")

    # Preserve subtitle separator
    filename = re.sub(r':', ' -', filename)
    
    return fix_encoding(filename)
    # valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    # return "".join([c for c in filename if c in valid_chars])

def meta_title(filename):
    """Title from pdf metadata.
    """

    fp = open(filename, 'rb')
    docinfo = PdfFileReader(fp).getDocumentInfo()
    fp.close()
    if docinfo is None:
        return ""
    return docinfo.title if docinfo.title else ""

def junk_line(line):
    """Judge if a line is not appropriate for a title.
    """
    too_small = len(line.strip()) < MIN_CHARS
    has_no_words = bool(re.search(r'^[0-9 \t-]+$|^(\(cid:[0-9 \t-]*\))+|^(abstract|unknown|title|untitled):?$', line.strip().lower()))
    is_copyright_info = bool(re.search(r'technical\s+report|proceedings|preprint|to\s+appear|submission|(integrated|international).*conference|transactions\s+on|symposium\s+on|downloaded\s+from\s+http', line.lower()))

    include_unexpected_keyword = any(unexpected_keyword in line.lower() for unexpected_keyword in UNEXPECTED_KEYWORDS)
    return too_small or has_no_words or is_copyright_info

def empty_str(s):
    return len(s.strip()) == 0

def update_largest_text(line, size, largest_text):
    line = line.replace('\r', '').replace('\n', '')
    size = round(size,2)
    log("===================================")
    log('text :' + line)
    log('update size :' + str(size))
    log('largest_text size: ' + str(largest_text['size']))
    if not empty_str(line):
        if (size > largest_text['size']):
            largest_text = {
                'contents': line,
                'size': size
            }
        # Title spans multiple lines
        elif (size == largest_text['size'] and largest_text['contents'].find(line) == -1):
            largest_text['contents'] = largest_text['contents'] + line
    return largest_text

def extract_largest_text(obj, largest_text):
    for child in obj:
        if isinstance(child, LTTextLine):
            log('lt_obj child line: ' + str(child))
            for child2 in child:
                if isinstance(child2, LTChar):
                    largest_text = update_largest_text(child.get_text(), child2.size, largest_text)
                    break
        elif isinstance(child, LTChar):
            largest_text = update_largest_text(obj.get_text(), child.size, largest_text)
            break
    return largest_text

def extract_figure_text(lt_obj, largest_text):
    """
    Extract text contained in a `LTFigure`.
    Since text is encoded in `LTChar` elements, we detect separate lines
    by keeping track of changes in font size.
    """
    text = ""
    line = ""
    size = 0
    char_distance = 0
    char_previous_x1 = 0
    state = CHAR_PARSING_STATE.INIT_X
    for child in lt_obj:
        log('child: ' + str(child))

        # Ignore other elements
        if not isinstance (child, LTChar):
            continue

        char_size = child.size
        char_text = child.get_text()
        decoded_char_text = unidecode.unidecode(char_text.encode('utf-8').decode('utf-8'))
        log('char: ' + str(char_size) + ' ' + str(decoded_char_text))

        # A new line was detected
        if char_size != size:
            log('new line')
            largest_text = update_largest_text(line, size, largest_text)
            text += line + '\n'
            line = char_text
            size = char_size

            char_previous_x1 = child.x1
            state = CHAR_PARSING_STATE.INIT_D
        # The same line
        else:
            # Spaces may not be present as `LTChar` elements,
            # so we manually add them.
            # NOTE: A word starting with lowercase can't be
            # distinguished from the current word.
            char_current_distance = abs(child.x0 - char_previous_x1)
            log('char_current_distance: ' + str(char_current_distance))
            log('char_distance: ' + str(char_distance))
            log('state: ' + str(state))

            # Initialization
            if state == CHAR_PARSING_STATE.INIT_X:
                char_previous_x1 = child.x1
                state = CHAR_PARSING_STATE.INIT_D
            elif state == CHAR_PARSING_STATE.INIT_D:
                # Update distance only if no space is detected
                if (char_distance > 0) and (char_current_distance < char_distance * 2.5):
                    char_distance = char_current_distance
                if (char_distance < 0.1):
                    char_distance = 0.1
                state = CHAR_PARSING_STATE.INSIDE_WORD
            # If the x-position decreased, then it's a new line
            if (state == CHAR_PARSING_STATE.INSIDE_WORD) and (child.x1 < char_previous_x1):
                log('x-position decreased')
                line += ' '
                char_previous_x1 = child.x1
                state = CHAR_PARSING_STATE.INIT_D
            # Large enough distance: it's a space
            elif (state == CHAR_PARSING_STATE.INSIDE_WORD) and (char_current_distance > char_distance * 8.5):
                log('space detected')
                log('char_current_distance: ' + str(char_current_distance))
                log('char_distance: ' + str(char_distance))
                line += ' '
                char_previous_x1 = child.x1
            # When larger distance is detected between chars, use it to
            # improve our heuristic
            elif (state == CHAR_PARSING_STATE.INSIDE_WORD) and (char_current_distance > char_distance) and (char_current_distance < char_distance * 2.5):
                char_distance = char_current_distance
                char_previous_x1 = child.x1
            # Chars are sequential
            else:
                char_previous_x1 = child.x1
            line += child.get_text()
    return (largest_text, text)

def pdf_text(filename):
    fp = open(filename, 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    rsrcmgr = PDFResourceManager()
    laparams = LAParams(all_texts=True)
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)

    text = ""
    largest_text = {
        'contents': "",
        'size': 0
    }
    pageno = 0
    titles = []

    for page in PDFPage.create_pages(doc):
        interpreter.process_page(page)
        layout = device.get_result()

        for lt_obj in layout:
            log('lt_obj: ' + str(lt_obj))
            if isinstance(lt_obj, (LTFigure, LTTextBox, LTTextLine)):
                if isinstance(lt_obj, LTFigure):
                    (largest_text, figure_text) = extract_figure_text(lt_obj, largest_text)
                    text += figure_text
                else:
                    largest_text = extract_largest_text(lt_obj, largest_text)
                    text += lt_obj.get_text() + '\n'
                titles.append(largest_text)
        pageno += 1
        # if title valid or page number is larger than 3 is break
        if bool(re.search(r'[a-zA-Z]+', text.strip(), flags=re.U)) or pageno > 3 :
            fp.close()
            break

    sorted_titles = sorted(titles, key=lambda o: o['size'],reverse=True)
    for title in sorted_titles:
        if valid_title(title["contents"]):
            return(title,text)

    return (largest_text, text)

def title_start(lines):
    for i, line in enumerate(lines):
        if not empty_str(line) and not junk_line(line):
            return i
    return 0

def title_end(lines, start, max_lines=2):
    for i, line in enumerate(lines[start+1:start+max_lines+1], start+1):
        if empty_str(line):
            return i
    return start + 1

def text_title(filename):
    """Extract title from PDF's text.
    """
    (largest_text, lines_joined) = pdf_text(filename)
    lines = lines_joined.strip().split('\n')

    if empty_str(largest_text['contents']):
        i = title_start(lines)
        j = title_end(lines, i)
        text = ' '.join(line.strip() for line in lines[i:j])
    else:
        text = largest_text['contents'].strip()

    # Strip dots, which conflict with os.path's splittext()
    text = re.sub(r'\.', '', text)

    return text

def valid_title(title):
    return not empty_str(title) and max_word_length(title) >= MIN_LONGEST_WORD and not junk_line(title) and empty_str(os.path.splitext(title)[1])

def pdf_title(filename):
    """Extract title using one of multiple strategies.
    """
    title = ""
    # try:
    #     title = meta_title(filename)
    #     if valid_title(title):
    #         return title
    # except:
    #     print("*** Skipping invalid metadata! ***")

    # try:
    title = text_title(filename)
    if valid_title(title):
        return title
    # except:
    #     print("*** Skipping invalid parsing! ***")

    if valid_title(title):
        return title

    return os.path.basename(os.path.splitext(filename)[0])

def process_file(directory, filename, rename, dry_run):
    title = pdf_title(filename)
    title = sanitize(' '.join(title.split()))

    if rename:
        new_name = os.path.join(directory, title + ".pdf")
        log ("%s => %s" % (filename, new_name))
        if not dry_run:
            if os.path.exists(new_name):
                print ("*** Target %s already exists! ***" % new_name)
            else:
                stat = os.stat(filename)
                os.rename(filename, new_name)
                os.utime(new_name, (stat.st_atime, stat.st_mtime))
    else:
        log ("%s => %s" % (filename, title))

    print(title)
    
def path_leaf(path):
    head, tail = os.path.split(path)
    return tail or os.path.basename(head)

def main():
    opts, args = getopt.getopt(sys.argv[1:], 'nd:', ['dry-run', 'rename'])

    dry_run = False
    rename = False
    target_dir = "."

    for opt, arg in opts:
        if opt in ['-n', '--dry-run']:
            dry_run = True
        elif opt in ['-r', '--rename']:
            rename = True
        elif opt in ['-d']:
            target_dir = arg

    if len(args) == 0:
        print ("Usage: %s [-d output] [--dry-run] [--rename] [filenames]\n" % path_leaf(sys.argv[0]))
        if ONE_CLICK_MODE:
            args = ['*.pdf']
            rename = True
        else:
            sys.exit(1)

    for filename in args:
        if "*" in filename:
            for filenameexpanded in glob.glob(filename):
                process_file(target_dir, filenameexpanded, rename, dry_run)
        else:
            process_file(target_dir, filename, rename, dry_run)
