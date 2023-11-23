def bar():
    a = 42
    print(a)
    return a << 2


def foo():
    print("hello world")
    bar()
    print("hello gab")


if __name__ == "__main__":
    foo()
