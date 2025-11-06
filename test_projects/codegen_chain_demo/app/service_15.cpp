#include "service_15.h"

Service15::Service15() {}

void Service15::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service15::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
