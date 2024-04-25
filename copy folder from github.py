command = "curl -JOL "
mylist = list()
link = input("Enter the link of a file:")
print("Enter files names:")
mylist.append(input())
while mylist[-1]!="":
    mylist.append(input())
mylist.pop()
link = link.replace(link.split("/")[-1],"")
for i in mylist:
    print(link+i)
