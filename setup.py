from setuptools import setup, find_packages

setup(
    name='just-start',
    version='0.4.0',
    description='Just Start is a wrapper for TaskWidget Warrior with pomodoro support',
    author='Ali Ghahraei Figueroa',
    author_email='aligf94@gmail.com',
    url='https://github.com/AliGhahraei/just-start',
    license='GPLv3',

    install_requires=['pexpect', 'toml', 'pydantic'],
    extras_require={
        'urwid': ['urwid'],

        # Just to be "installable" like the other clients
        'term': [],
    },
    packages=find_packages(),

    entry_points={
        'console_scripts': [
            'just-start-term = just_start.client_example:main[term]',
            'just-start-urwid = just_start_urwid:main[urwid]',
        ],
    }
)
