from tests.targets.target import bar


def foo():
    print("calling imported bar")
    bar()
    print("called imported bar")


foo()
