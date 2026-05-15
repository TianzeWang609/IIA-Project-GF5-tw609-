# GF5 Intro Slides

For quick viewing, open the online intro slides from the project page. To open
the same HTML locally without project-folder note saving, run:

```bash
python3 docs/build_site.py
python3 slides/build_slides.py
```

Then open `site/intro.html` in a browser.

To save your own notes locally, run this from the repository root:

```bash
python3 slides/serve.py
```

Then open `http://127.0.0.1:8095/intro.html`. Notes are saved in
`slides/student_notes/intro_notes.md`.
