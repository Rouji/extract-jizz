# Extract Jizz
Extracts archives (zip/rar) while trying to convert non-UTF-8 filenames and contents to UTF-8. 
Uses [chardet](https://github.com/chardet/chardet) to guess original encodings. 

Give it a directory and it will recursively look for any archives it knows how to extract in it. Does however not extract any archives nested in just extracted ones.

Doesn't preserve mtime or any other attributes.

For more info, look at the --help text or have a look at the code.

# May Produce Garbage
For archives that contain few files and/or these filenames are short or hard to guess for chardet, it may well get it wrong sometimes. 
If if can't guess an encoding at all, it defaults to decoding as SHIFT_JIS (a.k.a. shit-jizz), as I mainly deal with weird Japanese files. 

Works somewhat reliably for file contents, since chardet gets a lot more input to work with from them.

