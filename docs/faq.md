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

## 4. Why Does SMPL Not Load On Windows?

If the blocky/proxy assets load but the real SMPL asset does not, and the
`Use LBS` checkbox stays unavailable, check your PyTorch and NumPy versions.
This Windows failure is tracked in
[GitHub issue #1](https://github.com/CambridgeCVCourses/IIA-Project-GF5/issues/1).

The reported broken environment mixed `torch 2.10.0+cpu` with `numpy 2.4.4`.
That can produce PyTorch DLL loading errors and SMPLX-to-NumPy conversion
errors. One confirmed fix is:

```bash
conda activate gf5
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install numpy==1.26.4 --force-reinstall
```

Then test:

```bash
python -c "import torch; print(torch.__version__)"
python -c "import numpy; print(numpy.__version__)"
python -c "import smplx; print('smplx ok')"
```

Expected versions for this workaround are `torch 2.3.1+cpu` and
`numpy 1.26.4`.

If Windows also reports an OpenMP duplicate-runtime warning, run:

```bat
set KMP_DUPLICATE_LIB_OK=TRUE
python viewer\asset_viewer.py --smpl-model assets\smpl\models\SMPL_MALE.pkl
```
