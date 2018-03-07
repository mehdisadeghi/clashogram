from setuptools import setup

def readme():
    with open('README.rst', encoding='utf-8') as f:
        return f.read()

setup(name='Clashogram',
      version='0.1.24',
      description='Clash of Clans war moniting for telegram channels.',
      long_description=readme(),
      author='Mehdi Sadeghi',
      author_email='mehdi@mehdix.org',
      url='https://github.com/mehdisadeghi/clashogram',
      py_modules=['clashogram'],
      scripts=['clashogram.py'],
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
                   'Programming Language :: Python :: 3',
                   'Programming Language :: Python :: 3.1',
                   'Programming Language :: Python :: 3.2',
                   'Programming Language :: Python :: 3.3',
                   'Programming Language :: Python :: 3.4',
                   'Programming Language :: Python :: 3.5',
                   'Programming Language :: Python :: 3.6']
     )
