import setuptools

setuptools.setup(
    name="vietnamese-pdf-title",
    version="1.0.0",
    description="extracting vietnamese title from pdf",
    long_description_content_type="text/markdown",
    url="https://github.com/nguyenhiepvan/vietnamese-pdftitle",
    author="Nguyen Van Hiep",
    author_email="nguyenhiepvan.bka@gmail.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
    ],
    include_package_data=True,
    install_requires=[
        "PyPDF2"
    ],
    entry_points={
        'console_scripts': [
            'vnpdftitle = pdftitle:main',
        ],
    }
)
