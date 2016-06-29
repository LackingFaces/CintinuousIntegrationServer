from setuptools import setup

setup(name='AlgumNomeManeiro',
      version='1.0',
      description='Continuous integration script for git based development',
      url='http://github.com/AlgumacoisaAqui',
      author='<LackingFaces>',
      author_email='arueira95@gmail.com',
      license='GNU',
      install_requires=[
          'argparse',
		  'psycopg2', 
		  'pyyaml',
			'tendo'
      ],
      zip_safe=True)
