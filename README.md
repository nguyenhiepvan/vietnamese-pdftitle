# Propose

extracting pdf title

# Installation

clone project and run

```shell
python setup.py develop
```
**notice**: maybe need permissions

# Requirement
- python >= 3.7
- PyPDF2
- unidecode
- ftfy
- pdfminer

# Usage

```shell
vnpdftitle -d tmp --rename <your-pdf-file>
```

**notice:** if you want to ignore some words, add them to `unexpected_keywords.json`

