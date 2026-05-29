# GF5 Slides

For quick viewing, open the Parts 1&2 or Part 3 slides from the project page.
The Notes panel works there too; notes are cached in the browser on that
device.

To open the same HTML locally without project-folder note saving, run:

```bash
python3 docs/build_site.py
python3 slides/build_slides.py
python3 slides/build_slides.py --source slides/part3.md --output site/part3-slides.html
```

Then open `site/parts12-slides.html` or `site/part3-slides.html` in a browser.

To save your own notes as a Markdown file in the project folder, run this from
the repository root:

```bash
python3 slides/serve.py
```

Then open `http://127.0.0.1:8095/parts12-slides.html`. Notes are saved per
deck under `slides/student_notes/`, for example `parts12_notes.md`. The same
server also builds and serves `part3-slides.html`.
