import xml.dom.minidom as minidom
import dateutil.parser as parser
import os
import shutil
import sys
import re
import pycassa
from pycassa.pool import ConnectionPool

pool = ConnectionPool('kdp_keyspace', ['localhost:9160'])
col_fam = pycassa.ColumnFamily(pool, 'kdp_cf')

def parseHead(head_dom):
    # parese the head of an article
    head_dict = {}
    
    # title of the article
    if len(head_dom.getElementsByTagName("title")) > 0:
        head_dict['title'] = head_dom.getElementsByTagName("title")[0].lastChild.nodeValue
    # date
    head_dict['date'] = parser.parse(head_dom.getElementsByTagName("pubdata")[0].getAttribute('date.publication'))
    # url
    head_dict['ref'] = head_dom.getElementsByTagName("pubdata")[0].getAttribute("ex-ref")
    return head_dict

def parseSubject(f):
    # infer the subject from 'meta data online-section=xxx'
    subject = ""
    for line in f.readlines():
        if 'online_sections' in line:
            m = re.search('meta content\=(.+?) name="online_sections"', line)
            if m:
              subject = m.group(1)
            break
    return subject

def parseDesk(f):
    # infer the subject from 'meta data online-section=xxx'
    desk = ""
    for line in f.readlines():
        if 'dsk' in line:
            m = re.search('meta content\=\"(.+?) name=\"dsk\"', line)
            if m:
              desk = m.group(1)
              if desk.endswith('Desk\"'):
                  desk = desk[:-5]
            break
    return desk
            
def parseBody(body_dom):
    # parses the body of an article. right now we just stitch together paragraphs
    for blk in body_dom.getElementsByTagName("body.content")[0].getElementsByTagName("block"):
        if blk.getAttribute("class") == "full_text":
            return '\n\n'.join([p.lastChild.nodeValue for p in blk.getElementsByTagName("p")])

def parseArticle(art_dom):
    # parses a NYTimes's DOM article into dictionary for MongoDB
    art_dict = {}
    
    # parse the head
    art_dict['head'] = parseHead(art_dom.getElementsByTagName("head")[0])
    
    # parse the body
    art_dict['body'] = parseBody(art_dom.getElementsByTagName("body")[0])

    return art_dict

if __name__ == '__main__':

    corpus_dir = sys.argv[1]
    year = int(sys.argv[2])
    # connect go database
        
    # find all the datafiles
    tgz_path = corpus_dir + str(year) + "/"
    tgz_files = [(dirpath, f) \
                 for dirpath, dirnames, files in os.walk(tgz_path) \
                 for f in files if f.endswith(".tgz")]
        
    # initialized order counter
    counter = 0
            
    # process each tgz file
    for tgz_file in tgz_files: 
        print "Parsing %s ..." % (tgz_file,) # create tmp folders for data 
        if not os.path.exists("tmp"):
            os.makedirs("tmp")
            
        shutil.copy(os.path.join(*tgz_file), './tmp/')
        os.system('tar zxf ./tmp/' + tgz_file[1] + ' -C ./tmp/')
            
        # find all the xml files 
        xml_files = [(dirpath, f) \
                     for dirpath, dirnames, files in os.walk("./tmp/") \
                     for f in files if f.endswith("xml")]
            
        #inserts = []
        for xml_file in xml_files:
            with open(os.path.join(*xml_file)) as f: 
                # load file and create dom object 
                dom = minidom.parseString(f.read()) 
                nitf_dom = dom.getElementsByTagName("nitf")[0]
                nitf_dic = parseArticle(nitf_dom)
                id_str = xml_file[0][6:]+'/'+str(year)+'/'+xml_file[1]
                nitf_dic['id'] = id_str.encode('utf-8')
                if 'title' not in nitf_dic['head'] or \
                   nitf_dic['head']['title'].startswith("Paid Notice")  or \
                   nitf_dic['head']['title'].startswith("Listing"):
                   continue
                f.seek(0)
                nitf_dic['subject'] = parseSubject(f).encode('utf-8')
                #print("subject: " + nitf_dic['subject'])
                f.seek(0) # temporarily do it in two passes. Both can be done in one pass over file
                nitf_dic['desk'] = parseDesk(f).encode('utf-8')
                #print("desk:" + nitf_dic['desk'])
                nitf_dic['order'] = counter
                counter = counter + 1
                subject = nitf_dic['subject']+' '+nitf_dic['desk']
                #print('inserting..' + nitf_dic['id'].encode('utf-8') + ' ' + nitf_dic['head']['title'].encode('utf-8') + subject.encode('utf-8'))
                print('.'),
                col_fam.insert(nitf_dic['id'].encode('utf-8'), {'title' : nitf_dic['head']['title'].encode('utf-8'), 'subject' : subject.encode('utf-8')})
                if nitf_dic['body'] != None:
                    col_fam.insert(nitf_dic['id'].encode('utf-8'), {'body' : nitf_dic['body']})
                
                #print('id: ' , nitf_dic['id'], ' title: ', nitf_dic['head']['title']),
                #print(' subject: ', nitf_dic['subject'], ' desk: ', nitf_dic['desk'])
        shutil.rmtree("./tmp/")
    print('Done!')
