"""Linux 7.3 GPIO callbacks and registration ownership in a new candidate."""
import argparse, hashlib, json, shutil
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    shutil.copytree(args.parent, args.output)
    rel = 'source/platform/ruby/gpio.c'
    path = args.output / rel
    text = path.read_text()
    old = 'static void arc_gpio_set(struct gpio_chip *chip, unsigned offset, int value)'
    assert text.count(old) == 1
    text = text.replace(old, old.replace('static void', 'static int'), 1)
    start = text.index('static int arc_gpio_set(')
    end = text.index('static int __init arc_gpio_init', start)
    body = text[start:end]
    assert body.count('\tgpio_output(g, offset, value);\n') == 1
    body = body.replace('\tgpio_output(g, offset, value);\n', '\tgpio_output(g, offset, value);\n\treturn 0;\n', 1)
    text = text[:start] + body + text[end:]
    old = '\tgpiochip_add(&arc_gpio.chip);\n\n\treturn 0;'
    assert text.count(old) == 1
    text = text.replace(old, '\t/* Preserve registration failure instead of reporting an unusable chip. */\n\treturn gpiochip_add_data(&arc_gpio.chip, &arc_gpio);', 1)
    path.write_text(text, newline='\n')
    proof = json.loads((args.parent / 'result.json').read_text())
    proof.update(status='SOURCE_ONLY_LINUX73_GPIO_API_PENDING_BUILD', parent=str(args.parent), changed_sources={rel: sha(path)}, firmware_eligible=False)
    proof['files'] = {str(p.relative_to(args.output)): sha(p) for group in ('source','headers','kernel-overlay','providers') for p in (args.output / group).rglob('*') if p.is_file()}
    (args.output / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'status': proof['status'], 'changed_sources': proof['changed_sources']}, indent=2))

if __name__ == '__main__':
    main()
