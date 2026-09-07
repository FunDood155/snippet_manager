snippets=[
     {"sno":1,
        "name":"for loop",
        "cat":"loops",
        "code":"for i in range(0,n):"},
        {"sno":2,
            "name":"print stat",
            "cat":"print",
            "code":"print(key,value)"}
]


def add():
     snippet={"sno":1,
     "name":"snippet name",
     "cat":"snippet category",
     "code":"snippet content"}
     print("Enter details of ",len(snippets)+1," th snippet")
     snippet.update({"sno":len(snippets)+1})
     x=input("Enter snippet name : ")
     snippet.update({"name":x})
     y=input("Enter snippet category : ")
     snippet.update({"cat":y})
     z=input("Enter snippet content : ")
     snippet.update({"code":z})
     snippets.append(snippet)

def remove():
     x=input("Which snippet u wanna remove : ")
     for i in snippets:
          if(i["name"]==x):
               snippets.remove(i)

def display():
    # print(snippets)
    for i in snippets:
        for key,value in i.items():
            print(key.title()," : ",value)
        print()

def show_category():
     for i in snippets:
          print(i["cat"])

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
    