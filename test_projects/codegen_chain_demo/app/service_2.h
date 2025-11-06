#pragma once
#include <functional>
#include <vector>

class Service2 {
public:
    Service2();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
