from threading import Thread


def target():
    a = []
    for i in range(100):
        a.append(i)


def main():
    threads = []
    for _ in range(2):
        t = Thread(target=target)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
