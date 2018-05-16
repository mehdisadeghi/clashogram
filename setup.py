from setuptools import setup


def readme():
    with open('README.rst', encoding='utf-8') as f:
        return f.read()


setup(name='Clashogram',
      version='0.2.1',
      description='Clash of Clans war moniting for telegram channels.',
      long_description=readme(),
      long_description_content_type='text/x-rst',
      author='Mehdi Sadeghi',
      author_email='mehdi@mehdix.org',
      url='https://github.com/mehdisadeghi/clashogram',
      py_modules=['clashogram'],
      scripts=['clashogram.py'],
      entry_points={
        'console_scripts': ['clashogram=clashogram:main']
      },
      license='MIT',
      platforms='any',
      install_requires=['babel',
                        'requests',
                        'jdatetime',
                        'pytz',
                        'python-dateutil',
                        'click'],
      keywords=['games', 'telegram', 'coc', 'notification', 'clash of clans'],
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Console',
                   'Intended Audience :: End Users/Desktop',
                   'License :: OSI Approved :: MIT License',
                   'Natural Language :: Persian',
                   'Natural Language :: English',
                   'Programming Language :: Python :: 3.5',
                   'Programming Language :: Python :: 3.6'])
