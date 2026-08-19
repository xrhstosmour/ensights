# Thesis build. Requires XeLaTeX and biber, either from a local TeX Live
# installation or, with ENGINE=docker, from the official TeX Live image.
#
#   make            build the PDF
#   make watch      rebuild continuously while editing
#   make clean      remove build artefacts, keep the PDF
#   make distclean  remove build artefacts and the PDF
#   make ENGINE=docker  build inside the TeX Live container instead

MAIN := main
ENGINE ?= local

LATEXMK_FLAGS := -xelatex -interaction=nonstopmode -halt-on-error -file-line-error

ifeq ($(ENGINE),docker)
# Pinned by digest: the `latest` tag drifts, and an upstream TeX Live update
# once broke the Greek biblatex-apa strings this manuscript depends on.
RUN := docker run --rm -v "$(CURDIR)":/work -w /work texlive/texlive@sha256:1cb66a6dc31fe153369c5bb63549aea31c2ffb351613af67b182d84c8521fe89
else
RUN :=
endif

.PHONY: all watch clean distclean

all:
	$(RUN) latexmk $(LATEXMK_FLAGS) $(MAIN).tex

watch:
	$(RUN) latexmk $(LATEXMK_FLAGS) -pvc $(MAIN).tex

# -c keeps the PDF, -C removes it too. Neither touches the .tex sources.
clean:
	$(RUN) latexmk -c $(MAIN).tex

distclean:
	$(RUN) latexmk -C $(MAIN).tex
