# Cognitive Units â€” Appendix B Reference Implementation

This repository contains the **non-normative Python/Pydantic reference implementation** accompanying the paper:

**Cognitive Units: A Core Representational Artifact Model for Governed Cognitive Transformations in Operational Systems**
Eduardo SÃ¡nchez Santana

**Associated paper DOI:** add the Zenodo DOI here after the paper record is published.

## Scope

The implementation is a constructive implementation witness at the representation level. It demonstrates that the artifact distinctions described in the paper can coexist as explicit executable software structures.

It is **not** a production runtime, canonical Cognitive Unit implementation, cognitive architecture, workflow engine, storage layer, or domain implementation. The conceptual model in the paper remains authoritative.

## Repository contents

- `appendix_b_reference_impl.py` â€” frozen paper-version Python/Pydantic implementation.
- `requirements.txt` â€” supported Pydantic major version.
- `CITATION.cff` â€” citation metadata for the software repository/release.
- `CODE_SHA256.txt` â€” integrity hash for the frozen Python module.
- `SOURCE_MANIFEST.sha256` â€” integrity manifest for the public repository files.
- `SMOKE_TEST.md` â€” minimal execution and integrity check.
- `RELEASE_NOTES_v1.0.0.md` â€” first public release notes.
- `LICENSE` â€” MIT License applying to this software repository.

The manuscript source, including the explanatory Appendix B LaTeX, is distributed with the paper through Zenodo rather than duplicated in this software repository.

## Requirements

The manuscript target is:

- Python 3.11+
- Pydantic 2.x

Install the dependency with:

```bash
python -m pip install -r requirements.txt
```

## Run the reference implementation

```bash
python appendix_b_reference_impl.py
```

A successful execution completes with exit code `0`. The module contains executable assertions that exercise the reference profile.

## Frozen paper-version integrity

SHA-256:

```text
70ceaef97dde911a65fa5d0df23983128747e97680cbf1c85d6e79afd4916cf2  appendix_b_reference_impl.py
```

Do not modify this file in the `v1.0.0` release if the release is intended to correspond exactly to Revision 1 of the paper.

## Citation

Use GitHub's **Cite this repository** function after `CITATION.cff` is available on the default branch. Also cite the associated paper using its Zenodo DOI after publication.

## License

This software is released under the **MIT License**.

Copyright (c) 2026 Eduardo SÃ¡nchez Santana.

The MIT License permits use, copying, modification, merging, publication, distribution, sublicensing, and sale of copies of the software, subject to preservation of the copyright and license notice. See [`LICENSE`](LICENSE) for the complete terms.
