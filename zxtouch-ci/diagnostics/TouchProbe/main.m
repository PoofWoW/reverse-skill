#import <UIKit/UIKit.h>

// Ordinary public UIKit receiver. No hooks, injected code or private event APIs.
@interface ProbeView : UIView
@property(nonatomic, strong) UILabel *status;
@property(nonatomic, strong) NSMutableArray *rows;
@property(nonatomic, strong) NSMapTable<UITouch *, NSNumber *> *identifiers;
@property(nonatomic, strong) NSArray *active;
@property NSUInteger nextID, peak, dropped;
@end
@implementation ProbeView
- (instancetype)init {
    if ((self = [super initWithFrame:CGRectZero])) {
        self.multipleTouchEnabled = YES;
        self.backgroundColor = [UIColor colorWithRed:0.12 green:0.2 blue:0.29 alpha:1];
        self.rows = [NSMutableArray array];
        self.identifiers = [NSMapTable weakToStrongObjectsMapTable];
        self.active = @[];
        self.nextID = 1;
        self.status = [UILabel new];
        self.status.textColor = UIColor.whiteColor;
        self.status.numberOfLines = 0;
        self.status.userInteractionEnabled = NO;
        [self addSubview:self.status];
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(interrupted:)
            name:UIApplicationWillResignActiveNotification object:nil];
        [self updateStatus];
    }
    return self;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    self.status.frame = CGRectMake(12, 12, self.bounds.size.width-24, 100);
}
- (void)append:(NSDictionary *)row {
    [self.rows addObject:row];
    if (self.rows.count > 5000) { [self.rows removeObjectAtIndex:0]; ++self.dropped; }
}
- (NSArray *)pack:(NSSet<UITouch *> *)touches {
    NSMutableArray *result = [NSMutableArray array];
    for (UITouch *touch in touches) {
        if (touch.view != self) continue;
        NSNumber *identifier = [self.identifiers objectForKey:touch];
        if (!identifier) { identifier = @(self.nextID++); [self.identifiers setObject:identifier forKey:touch]; }
        CGPoint point = [touch locationInView:self];
        [result addObject:@{@"id":identifier,@"phase":@(touch.phase),@"x":@(point.x),@"y":@(point.y),
            @"timestamp":@(touch.timestamp),@"type":@(touch.type)}];
    }
    return result;
}
- (void)record:(NSString *)kind touches:(NSSet<UITouch *> *)changed event:(UIEvent *)event {
    NSArray *all = [self pack:event.allTouches];
    NSMutableArray *active = [NSMutableArray array];
    for (NSDictionary *touch in all) {
        NSInteger phase = [touch[@"phase"] integerValue];
        if (phase == UITouchPhaseBegan || phase == UITouchPhaseMoved || phase == UITouchPhaseStationary)
            [active addObject:touch];
    }
    self.active = active;
    self.peak = MAX(self.peak, active.count);
    [self append:@{@"kind":kind,@"wall":@([NSDate date].timeIntervalSince1970),
        @"timestamp":@(event.timestamp),@"allTouches":all,@"changedTouches":[self pack:changed],
        @"active":active,@"activeCount":@(active.count)}];
    for (UITouch *touch in changed)
        if (touch.phase == UITouchPhaseEnded || touch.phase == UITouchPhaseCancelled)
            [self.identifiers removeObjectForKey:touch];
    [self updateStatus]; [self setNeedsDisplay];
}
- (void)updateStatus {
    self.status.text = [NSString stringWithFormat:@"UIKit active=%lu / peak=%lu\nIDs=%@\nrows=%lu / dropped=%lu",
        (unsigned long)self.active.count,(unsigned long)self.peak,[self.active valueForKey:@"id"],
        (unsigned long)self.rows.count,(unsigned long)self.dropped];
}
- (void)interrupted:(NSNotification *)notification {
    [self append:@{@"kind":@"resign-active",@"wall":@([NSDate date].timeIntervalSince1970),@"activeBefore":self.active}];
    self.active = @[]; [self.identifiers removeAllObjects]; [self updateStatus]; [self setNeedsDisplay];
}
- (void)touchesBegan:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e { [self record:@"began" touches:t event:e]; }
- (void)touchesMoved:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e { [self record:@"moved" touches:t event:e]; }
- (void)touchesEnded:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e { [self record:@"ended" touches:t event:e]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e { [self record:@"cancelled" touches:t event:e]; }
- (void)drawRect:(CGRect)rect {
    for (NSDictionary *touch in self.active) {
        CGFloat x=[touch[@"x"] doubleValue], y=[touch[@"y"] doubleValue];
        [[UIColor colorWithHue:([touch[@"id"] unsignedIntegerValue]%10)/10.0 saturation:0.7 brightness:1 alpha:1] setFill];
        [[UIBezierPath bezierPathWithOvalInRect:CGRectMake(x-22,y-22,44,44)] fill];
        [[touch[@"id"] description] drawAtPoint:CGPointMake(x+26,y)
            withAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor,NSFontAttributeName:[UIFont systemFontOfSize:18]}];
    }
}
@end

@interface ProbeController : UIViewController
@property(nonatomic, strong) ProbeView *probe;
@end
@implementation ProbeController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.probe = [ProbeView new];
    UILabel *help = [UILabel new]; help.textColor=UIColor.whiteColor; help.numberOfLines=0;
    help.text=@"Disable ZXTouch indicator. All fingers in blue area.\nTwo stable IDs, independent movement/release, then active=0.\nExport receiver log after lifting all fingers.";
    UIButton *reset=[UIButton buttonWithType:UIButtonTypeSystem]; [reset setTitle:@"Reset" forState:UIControlStateNormal];
    [reset addTarget:self action:@selector(reset) forControlEvents:UIControlEventTouchUpInside];
    UIButton *export=[UIButton buttonWithType:UIButtonTypeSystem]; [export setTitle:@"Export JSON" forState:UIControlStateNormal];
    [export addTarget:self action:@selector(exportLog:) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *buttons=[[UIStackView alloc] initWithArrangedSubviews:@[reset,export]];
    buttons.distribution=UIStackViewDistributionFillEqually;
    UIStackView *stack=[[UIStackView alloc] initWithArrangedSubviews:@[help,buttons,self.probe]];
    stack.axis=UILayoutConstraintAxisVertical;stack.spacing=10;stack.translatesAutoresizingMaskIntoConstraints=NO;
    [self.view addSubview:stack];
    UILayoutGuide *safe=self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[[stack.topAnchor constraintEqualToAnchor:safe.topAnchor constant:10],
        [stack.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [stack.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:10],
        [stack.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-10],
        [self.probe.heightAnchor constraintGreaterThanOrEqualToConstant:200]]];
}
- (void)reset {
    if(self.probe.active.count) return;
    [self.probe.rows removeAllObjects];self.probe.peak=0;self.probe.dropped=0;
    [self.probe updateStatus];
}
- (void)exportLog:(UIButton *)button {
    if(self.probe.active.count) return;
    NSDictionary *payload=@{@"schema":@1,@"layer":@"UIKit receiver (public UIEvent.allTouches)",
        @"os":UIDevice.currentDevice.systemVersion,@"peak":@(self.probe.peak),
        @"dropped":@(self.probe.dropped),@"rows":self.probe.rows};
    NSData *data=[NSJSONSerialization dataWithJSONObject:payload options:NSJSONWritingPrettyPrinted error:nil];
    NSURL *url=[[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    url=[url URLByAppendingPathComponent:@"zxtouch-native-receiver.json"];
    if(![data writeToURL:url atomically:YES]) return;
    UIActivityViewController *share=[[UIActivityViewController alloc] initWithActivityItems:@[url] applicationActivities:nil];
    share.popoverPresentationController.sourceView=button;
    share.popoverPresentationController.sourceRect=button.bounds;
    [self presentViewController:share animated:YES completion:nil];
}
@end
@interface ProbeDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation ProbeDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[ProbeController new];[self.window makeKeyAndVisible];return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(ProbeDelegate.class)); }
}
