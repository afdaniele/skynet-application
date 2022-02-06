ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
PART=patch
PROJECT_NAME=skynet_application
REPOSITORY_NAME=skynet

all:

new-dist:
	$(MAKE) clean bump-upload

bump-upload:
	$(MAKE) bump upload

bump:
	bumpversion ${PART}

upload:
	$(MAKE) clean
	$(MAKE) build
	twine upload dist/* -r ${REPOSITORY_NAME}
	$(MAKE) clean

build:
	$(MAKE) assert-not-dirty
	python3 setup.py sdist

install:
	python3 setup.py install --record files.txt

clean:
	rm -rf dist/ build/ ${PROJECT_NAME}.egg-info/ MANIFEST

uninstall:
	xargs rm -rf < files.txt

format:
	yapf -r -i -p -vv ${ROOT_DIR}

test:
	$(MAKE) test-unit

test-unit:
	$(MAKE) test-one-unit TEST="test_*"

test-one-unit:
	@echo "Running unit tests:"; echo ""
	@PYTHONPATH="${ROOT_DIR}:$${PYTHONPATH}" \
		python3 \
			-m unittest discover \
			--verbose \
			-s "${ROOT_DIR}/tests/unit" \
			-p "${TEST}.py"

assert-not-dirty:
	@[ -z "$(shell git status --porcelain ${ROOT_DIR})" ] || \
		{ echo "\n\nERROR: There are uncommitted changes in the package's directory. Please commit them first.\n\n"; exit 1; }
