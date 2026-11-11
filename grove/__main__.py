import sys

from .app import GroveApplication


def main():
    return GroveApplication().run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
