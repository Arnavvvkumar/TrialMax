from chalkcompute import Image, Sandbox

sandbox = Sandbox(
    image=Image.debian_slim("3.12"),
    lifetime="300s",
).run()

try:
    result = sandbox.exec(
        "python", "-c", "print('Hello from Chalk!')"
    )
    print(result.stdout_text, end="")
finally:
    sandbox.terminate()
