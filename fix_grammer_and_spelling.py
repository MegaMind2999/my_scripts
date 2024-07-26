## Installing Library
!pip install lmproof

## Importing Library
import lmproof as lm

## Function for proofreading 
def Proofread(text):
    proof = lm.load("en")
    error_free_text = proof.proofread(text)
    return error_free_text

## Sample Text
TEXT = '' ## Place sample Text here

## Function Call 
Print(Proofread(TEXT))