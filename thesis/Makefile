# Thesis build. Requires XeLaTeX and bibtex, either from a local TeX Live
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
# The class sets Arial and Courier New, which no TeX distribution ships.
# Docker Desktop refuses to mount the system font directory, so the faces the
# class needs are staged into an ignored directory and mounted into the
# container font path. The fonts themselves never enter the repository.
HOSTFONTS ?= /System/Library/Fonts/Supplemental
FONTDIR := .fonts
RUN := docker run --rm -v "$(CURDIR)":/work \
	-v "$(CURDIR)/$(FONTDIR)":/usr/local/share/fonts:ro \
	-w /work texlive/texlive@sha256:1cb66a6dc31fe153369c5bb63549aea31c2ffb351613af67b182d84c8521fe89
else
RUN :=
endif

.PHONY: all fonts watch clean distclean


all: fonts
	$(RUN) ./build.sh $(LATEXMK_FLAGS) $(MAIN).tex

# Stage the class fonts for the container. A no-op outside docker builds.
fonts:
	mkdir -p $(FONTDIR)
	cp -n "$(HOSTFONTS)"/Arial.ttf "$(HOSTFONTS)"/Arial\ Bold.ttf \
		"$(HOSTFONTS)"/Arial\ Italic.ttf "$(HOSTFONTS)"/Arial\ Bold\ Italic.ttf \
		"$(HOSTFONTS)"/Courier\ New.ttf "$(HOSTFONTS)"/Courier\ New\ Bold.ttf \
		"$(HOSTFONTS)"/Courier\ New\ Italic.ttf \
		"$(HOSTFONTS)"/Courier\ New\ Bold\ Italic.ttf $(FONTDIR)/ 2>/dev/null || true

watch: fonts
	$(RUN) ./build.sh $(LATEXMK_FLAGS) -pvc $(MAIN).tex

# -c keeps the PDF, -C removes it too. Neither touches the .tex sources.
clean:
	$(RUN) ./build.sh -c $(MAIN).tex

distclean:
	$(RUN) ./build.sh -C $(MAIN).tex
