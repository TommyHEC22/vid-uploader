def filter_love_quotes():
    #choose love quotes less than 250 characters.
    import csv
    from ftfy import fix_text

    with open("quotes.csv", newline="", encoding="latin1") as infile, \
         open("love_quotes.csv", "w", newline="", encoding="utf-8") as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        for row in reader:
            quote = str(row[0])
            author = str(row[1])
            category = str(row[2])

            quote = fix_text(quote)
            author = fix_text(author)
            category = fix_text(category)

            if "," in quote and ", " not in quote:
                quote = quote.replace(",", ", ")

            if "." in quote and ". " not in quote:
                quote = quote.replace(".", ". ")

            if "..." in quote and "... " not in quote:
                quote = quote.replace("...", "... ")

            if "!" in quote and "! " not in quote:
                quote = quote.replace("!", "! ")

            if "?" in quote and "? " not in quote:
                quote = quote.replace("?", "? ")

            if '"' in quote:
                continue

            if len(quote) < 180 and "love" in category:
                writer.writerow([quote, author, category])


def shorten_love_quotes():
    #shorten love quotes to less than 180 characters.
    import csv
    from ftfy import fix_text

    with open("love_quotes.csv", newline="", encoding="utf-8") as infile, \
         open("short_love_quotes.csv", "w", newline="", encoding="utf-8") as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        for row in reader:
            quote = str(row[0])
            author = str(row[1])
            category = str(row[2])

            quote = fix_text(quote)
            author = fix_text(author)
            category = fix_text(category)

            if len(quote) < 140:
                writer.writerow([quote, author, category])


shorten_love_quotes()