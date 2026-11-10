import sys

from .app import SpoolApplication


def main():
    return SpoolApplication().run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
