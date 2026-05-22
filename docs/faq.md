# Frequently Asked Questions

## 1. Can I Use `conda` Instead Of `mamba`?

Yes. In the setup instructions, you can replace `mamba` with `conda` in the
environment commands.

For example:

```bash
conda env create -f env.yml
conda activate gf5
conda env update -f env.yml --prune
```

`mamba` is a drop-in replacement for `conda` with faster environment
resolution. The resulting `gf5` environment should be the same.

## 2. Can I Keep My Custom Code In My Own Git Repository?

Yes. You can set up two Git remotes for your local repository:

- one remote for pulling updates from the teaching repository
- one remote for pushing your own custom code to your personal repository

For example:

```bash
git remote rename origin teaching
git remote add myrepo git@github.com:YOUR_USERNAME/YOUR_REPO.git
```

Then pull course updates from the teaching repository:

```bash
git pull teaching main
```

and push your own work to your repository:

```bash
git push myrepo main
```

Use your actual repository URL in place of
`git@github.com:YOUR_USERNAME/YOUR_REPO.git`.

## 3. Which SMPL Model Should I Download?

See [Part 2: SMPL Model Setup](part2.md#smpl-model-setup) for the detailed
download instructions. The short version is: use the standard SMPL body model
download, unzip it, and place the extracted `smpl/` folder inside `assets/` so
the model files appear under:

```text
assets/smpl/models/
```
