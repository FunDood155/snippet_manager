import json

with open("snippets.json","r") as f:
     snippets=json.load(f)

def add():
    snippet = {
        "sno": len(snippets) + 1,
        "name": input("Enter snippet name : "),
        "cat": input("Enter snippet category : "),
        "code": input("Enter snippet content : ")
    }
    found=False
    for i in snippets:
        if(i["name"]==snippet["name"]):
            print("Snippet already exists")
            found=True
            break
    if not found:
        snippets.append(snippet)
        with open("snippets.json","w") as f:
            json.dump(snippets,f,indent=4)

def remove():
    x=input("Which snippet u wanna remove : ")
    found = False
    for i in snippets:
        if i["name"] == x:
            snippets.remove(i)
            with open("snippets.json","w") as f:
                json.dump(snippets,f,indent=4)
            print("Snippet ",x," removed")
            found = True
            break
    if not found:
        print("Snippet not found")

def display():
    # print(snippets)
    for i in snippets:
        for key,value in i.items():
            print(key.title()," : ",value)
        print()

def show_category():
    categories = set()
    for i in snippets:
        categories.add(i["cat"])
    for cat in categories:
        print(cat)

def show_snippets():
    for i in snippets:
        print(i["name"])

print("1.Add")
print("2.Remove")
print("3.Display")
print("4.Show all category")
print("5.Show all snippets")

ch=True
while(ch):
    ch=input("Enter ur choice : ")
    if(ch=='1'):add()
    elif(ch=='2'):remove()
    elif(ch=='3'):display()
    elif(ch=='4'):show_category()
    elif(ch=='5'):show_snippets()
    else:break
    