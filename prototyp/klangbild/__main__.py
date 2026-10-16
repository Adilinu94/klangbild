import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "golden":
        from .golden import main

        sys.exit(main(sys.argv[2:]))
    else:
        from .pipeline import main

        sys.exit(main())
